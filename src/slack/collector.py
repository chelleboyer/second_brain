"""Slack message collector — read-only polling via conversations.history."""

import asyncio
from typing import Any

import structlog
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from src.core.exceptions import SlackCollectionError
from src.storage.repository import BrainEntryRepository

log = structlog.get_logger(__name__)


class SlackCollector:
    """Collects messages from Slack channel + bot DMs via polling."""

    def __init__(
        self,
        client: WebClient,
        channel_id: str,
        repository: BrainEntryRepository,
        collect_dms: bool = True,
    ) -> None:
        self.client = client
        self.channel_id = channel_id
        self.repository = repository
        self.collect_dms = collect_dms
        self._user_cache: dict[str, str] = {}

    async def collect_new_messages(self) -> list[dict[str, Any]]:
        """Fetch new messages since last processed timestamp.

        Returns list of message dicts with keys:
        ts, text, user, user_name, permalink, thread_ts, reply_count
        """
        last_ts = await self.repository.get_last_processed_ts()
        log.info("collecting_messages", last_ts=last_ts, channel=self.channel_id)

        all_messages: list[dict[str, Any]] = []

        try:
            # Collect from main channel
            channel_msgs = await self._fetch_channel_history(
                self.channel_id, last_ts
            )
            all_messages.extend(channel_msgs)

            # Collect from bot DMs if enabled
            if self.collect_dms:
                dm_msgs = await self._fetch_dm_messages(last_ts)
                all_messages.extend(dm_msgs)

            # Update last processed timestamp to the newest message
            if all_messages:
                newest_ts = max(msg["ts"] for msg in all_messages)
                await self.repository.set_last_processed_ts(newest_ts)
                log.info(
                    "messages_collected",
                    count=len(all_messages),
                    newest_ts=newest_ts,
                )
            else:
                log.info("no_new_messages")

        except SlackApiError as e:
            raise SlackCollectionError(
                f"Slack API error: {e.response['error']}",
                details={"error": e.response["error"]},
            ) from e

        return all_messages

    async def _fetch_channel_history(
        self, channel_id: str, oldest: str | None
    ) -> list[dict[str, Any]]:
        """Fetch all messages from a channel with full pagination."""
        messages: list[dict[str, Any]] = []
        cursor: str | None = None

        while True:
            kwargs: dict[str, Any] = {
                "channel": channel_id,
                "limit": 200,
            }
            if oldest:
                kwargs["oldest"] = oldest
            if cursor:
                kwargs["cursor"] = cursor

            # Slack SDK is sync — run in thread
            response = await asyncio.to_thread(
                self.client.conversations_history, **kwargs
            )

            for msg in response.get("messages", []):
                # Filter out bot messages and system messages
                if msg.get("subtype"):
                    continue
                if not msg.get("text"):
                    continue

                processed = await self._process_message(msg, channel_id)
                if processed:
                    messages.append(processed)

            # Check pagination
            if response.get("has_more"):
                cursor = (
                    response.get("response_metadata", {}).get("next_cursor")
                )
                if not cursor:
                    break
            else:
                break

        return messages

    async def _fetch_dm_messages(
        self, oldest: str | None
    ) -> list[dict[str, Any]]:
        """Fetch messages from bot DM channels."""
        messages: list[dict[str, Any]] = []

        try:
            # Find bot IM channels
            response = await asyncio.to_thread(
                self.client.conversations_list, types="im", limit=100
            )
            im_channels = response.get("channels", [])

            for im in im_channels:
                im_id = im.get("id")
                if im_id:
                    dm_msgs = await self._fetch_channel_history(im_id, oldest)
                    messages.extend(dm_msgs)

        except SlackApiError as e:
            log.warning(
                "dm_collection_failed",
                error=e.response.get("error", str(e)),
            )

        return messages

    async def _process_message(
        self, msg: dict, channel_id: str
    ) -> dict[str, Any] | None:
        """Extract structured data from a raw Slack message."""
        ts = msg.get("ts", "")
        text = msg.get("text", "")
        user_id = msg.get("user", "unknown")

        if not text.strip():
            return None

        # Resolve user display name (cached)
        user_name = await self._resolve_user_name(user_id)

        # Get permalink
        permalink = await self._get_permalink(channel_id, ts)

        return {
            "ts": ts,
            "text": text,
            "user": user_id,
            "user_name": user_name,
            "permalink": permalink,
            "thread_ts": msg.get("thread_ts"),
            "reply_count": msg.get("reply_count", 0),
        }

    async def _resolve_user_name(self, user_id: str) -> str:
        """Resolve Slack user ID to display name, with caching."""
        if user_id in self._user_cache:
            return self._user_cache[user_id]

        try:
            response = await asyncio.to_thread(
                self.client.users_info, user=user_id
            )
            user_info = response.get("user", {})
            display_name = (
                user_info.get("profile", {}).get("display_name")
                or user_info.get("real_name")
                or user_id
            )
            self._user_cache[user_id] = display_name
            return display_name
        except SlackApiError:
            self._user_cache[user_id] = user_id
            return user_id

    async def _get_permalink(self, channel_id: str, message_ts: str) -> str:
        """Get permalink for a Slack message."""
        try:
            response = await asyncio.to_thread(
                self.client.chat_getPermalink,
                channel=channel_id,
                message_ts=message_ts,
            )
            return response.get("permalink", "")
        except SlackApiError:
            return ""
