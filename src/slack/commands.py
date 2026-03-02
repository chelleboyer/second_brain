"""Slack slash command handler — processes /brain commands via webhook."""

from __future__ import annotations

import structlog

log = structlog.get_logger(__name__)


class SlackCommandHandler:
    """Processes /brain slash commands from Slack.

    Commands:
        /brain capture <text>     — Manual capture with entity extraction feedback
        /brain recall <query>     — Entity-aware contextual recall
        /brain entity <name>      — Show entity brief + linked entries
        /brain summarize <target> — Progressive summary for entity or project
        /brain help               — Show available commands

    This handler is designed to be called from a FastAPI webhook endpoint.
    Each method returns a Slack-formatted response dict.
    """

    def __init__(
        self,
        pipeline=None,
        recall_service=None,
        entity_repo=None,
        summarization_service=None,
        search=None,
    ) -> None:
        self.pipeline = pipeline
        self.recall_service = recall_service
        self.entity_repo = entity_repo
        self.summarization_service = summarization_service
        self.search = search

    async def handle(self, command_text: str) -> dict:
        """Route a /brain command to the appropriate handler.

        Args:
            command_text: The text after /brain (e.g., "capture This is an idea")

        Returns:
            Slack message payload dict with 'text' and optional 'blocks'.
        """
        parts = command_text.strip().split(maxsplit=1)
        if not parts:
            return self._help_response()

        action = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""

        handlers = {
            "capture": self._handle_capture,
            "recall": self._handle_recall,
            "entity": self._handle_entity,
            "summarize": self._handle_summarize,
        }

        if action == "help":
            return self._help_response()

        handler = handlers.get(action)
        if not handler:
            return {
                "response_type": "ephemeral",
                "text": f"Unknown command: `{action}`. Use `/brain help` for available commands.",
            }

        try:
            return await handler(arg)
        except Exception as e:
            log.error("slash_command_failed", action=action, error=str(e), exc_info=True)
            return {
                "response_type": "ephemeral",
                "text": f"Something went wrong: {str(e)[:200]}",
            }

    async def _handle_capture(self, text: str) -> dict:
        """Handle /brain capture <text> — capture with entity extraction feedback."""
        if not text.strip():
            return {
                "response_type": "ephemeral",
                "text": "Usage: `/brain capture <your thought>`",
            }

        if not self.pipeline:
            return {"response_type": "ephemeral", "text": "Capture service not available."}

        entry = await self.pipeline.capture_manual(text)

        # Build response with entity extraction feedback
        entities_text = ""
        if entry.extracted_entities:
            entity_pills = ", ".join(f"`{e}`" for e in entry.extracted_entities)
            entities_text = f"\n*Entities extracted:* {entity_pills}"

        novelty_text = ""
        if entry.novelty.value == "augment":
            novelty_text = "\n↗️ This augments an existing entry."
        elif entry.novelty.value == "duplicate":
            novelty_text = "\n♻️ This appears to be a duplicate."

        para_text = f" | 📂 {entry.para_category.value.title()}"

        return {
            "response_type": "in_channel",
            "text": (
                f"✅ *Captured:* {entry.title}\n"
                f"_{entry.summary}_\n"
                f"Type: {entry.type.value}{para_text} | Confidence: {entry.confidence:.0%}"
                f"{entities_text}{novelty_text}"
            ),
        }

    async def _handle_recall(self, query: str) -> dict:
        """Handle /brain recall <query> — entity-aware contextual recall."""
        if not query.strip():
            return {
                "response_type": "ephemeral",
                "text": "Usage: `/brain recall <your question>`",
            }

        if not self.recall_service:
            return {"response_type": "ephemeral", "text": "Recall service not available."}

        result = await self.recall_service.recall_simple(question=query, limit=5)

        if not result.sources:
            return {
                "response_type": "ephemeral",
                "text": f"No entries found for: _{query}_",
            }

        lines = [f"🔍 *Recall results for:* _{query}_\n"]
        for i, source in enumerate(result.sources[:5], 1):
            score_text = ""
            if i <= len(result.search_results):
                score_text = f" ({result.search_results[i-1].score:.0%})"
            lines.append(
                f"{i}. *{source.title}*{score_text}\n"
                f"   _{source.summary[:150]}_\n"
                f"   {source.type.value} | {source.created_at.strftime('%Y-%m-%d')}"
            )

        lines.append(f"\n_Confidence: {result.confidence:.0%} | {len(result.sources)} sources_")

        return {
            "response_type": "in_channel",
            "text": "\n".join(lines),
        }

    async def _handle_entity(self, name: str) -> dict:
        """Handle /brain entity <name> — show entity brief + linked entries."""
        if not name.strip():
            return {
                "response_type": "ephemeral",
                "text": "Usage: `/brain entity <entity name>`",
            }

        if not self.entity_repo:
            return {"response_type": "ephemeral", "text": "Entity service not available."}

        entities = await self.entity_repo.search_entities_by_name(name)
        if not entities:
            return {
                "response_type": "ephemeral",
                "text": f"No entity found matching: _{name}_",
            }

        entity = entities[0]  # Best match
        entry_ids = await self.entity_repo.get_entries_for_entity(entity.id)

        aliases_text = ""
        if entity.aliases:
            aliases_text = f"\n*Aliases:* {', '.join(entity.aliases)}"

        desc_text = ""
        if entity.description:
            desc_text = f"\n_{entity.description}_"

        return {
            "response_type": "in_channel",
            "text": (
                f"🏗️ *Entity:* {entity.name} ({entity.entity_type.value})\n"
                f"📊 {entity.entry_count} linked entries{aliases_text}{desc_text}\n"
                f"_Last updated: {entity.updated_at.strftime('%Y-%m-%d')}_"
            ),
        }

    async def _handle_summarize(self, target: str) -> dict:
        """Handle /brain summarize <entity|project> — progressive summary."""
        if not target.strip():
            return {
                "response_type": "ephemeral",
                "text": "Usage: `/brain summarize <entity or project name>`",
            }

        if not self.entity_repo or not self.summarization_service:
            return {"response_type": "ephemeral", "text": "Summarization service not available."}

        entities = await self.entity_repo.search_entities_by_name(target)
        if not entities:
            return {
                "response_type": "ephemeral",
                "text": f"No entity found matching: _{target}_",
            }

        entity = entities[0]
        summary = await self.summarization_service.summarize_entity(
            entity.id, force=False
        )

        if not summary:
            return {
                "response_type": "ephemeral",
                "text": f"Could not generate summary for _{entity.name}_. Ensure LLM provider is configured.",
            }

        return {
            "response_type": "in_channel",
            "text": (
                f"📝 *Summary for {entity.name}:*\n\n"
                f"{summary.summary_text}\n\n"
                f"_Based on {summary.entry_count_at_summary} entries "
                f"| Updated {summary.updated_at.strftime('%Y-%m-%d')}_"
            ),
        }

    @staticmethod
    def _help_response() -> dict:
        """Return help text listing all available commands."""
        return {
            "response_type": "ephemeral",
            "text": (
                "🧠 *Second Brain Commands*\n\n"
                "• `/brain capture <text>` — Capture and classify a thought\n"
                "• `/brain recall <query>` — Search your knowledge base\n"
                "• `/brain entity <name>` — View entity brief and linked entries\n"
                "• `/brain summarize <name>` — Generate summary for an entity\n"
                "• `/brain help` — Show this help message"
            ),
        }
