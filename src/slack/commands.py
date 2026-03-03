"""Slack slash command handler — processes /brain commands via webhook."""

from __future__ import annotations

import re

import structlog

from src.models.enums import AssetCategory, InitiativeType, VisibilityLevel

log = structlog.get_logger(__name__)


class SlackCommandHandler:
    """Processes /brain slash commands from Slack.

    Commands:
        /brain capture <text>               — Manual capture with entity extraction feedback
        /brain recall <query>               — Entity-aware contextual recall
        /brain entity <name>                — Show entity brief + linked entries
        /brain summarize <target>           — Progressive summary for entity or project
        /brain initiative <title> [desc]    — Create a scored initiative
        /brain stakeholder <name> [role]    — Track a new stakeholder
        /brain asset <title> [desc]         — Track a strategic asset
        /brain help                         — Show available commands

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
        strategy_repo=None,
        evaluation_engine=None,
    ) -> None:
        self.pipeline = pipeline
        self.recall_service = recall_service
        self.entity_repo = entity_repo
        self.summarization_service = summarization_service
        self.search = search
        self.strategy_repo = strategy_repo
        self.evaluation_engine = evaluation_engine

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
            "initiative": self._handle_initiative,
            "stakeholder": self._handle_stakeholder,
            "asset": self._handle_asset,
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

    # ── Strategy commands ─────────────────────────────────────────

    @staticmethod
    def _parse_quoted_title(text: str) -> tuple[str, str]:
        """Parse 'title rest' or '"quoted title" rest' from text.

        Returns (title, remainder). Supports both quoted and unquoted forms.
        """
        text = text.strip()
        match = re.match(r'^"([^"]+)"\s*(.*)', text)
        if match:
            return match.group(1).strip(), match.group(2).strip()
        # Fallback: first word is title
        parts = text.split(maxsplit=1)
        return parts[0], parts[1] if len(parts) > 1 else ""

    async def _handle_initiative(self, text: str) -> dict:
        """Handle /brain initiative "Title" [description] — create a scored initiative.

        Examples:
            /brain initiative "API Redesign" Rebuild the public API layer
            /brain initiative "Tech Talk" Quick scored initiative
        """
        if not text.strip():
            return {
                "response_type": "ephemeral",
                "text": (
                    "Usage: `/brain initiative \"Title\" [description]`\n"
                    "Creates a scored initiative with default scores. "
                    "Use the web UI to adjust scoring."
                ),
            }

        if not self.evaluation_engine:
            return {"response_type": "ephemeral", "text": "Strategy service not available."}

        from src.models.strategy import InitiativeCreate

        title, description = self._parse_quoted_title(text)

        create = InitiativeCreate(
            title=title,
            description=description,
            initiative_type=InitiativeType.SCORED,
        )

        initiative = await self.evaluation_engine.evaluate_initiative(create)

        return {
            "response_type": "in_channel",
            "text": (
                f"♟️ *Initiative created:* {initiative.title}\n"
                f"Category: {initiative.category.value.title()} "
                f"| Score: {initiative.scores.total}/25 "
                f"| Visibility: {initiative.visibility.value}\n"
                f"_{initiative.description[:200]}_" if initiative.description else
                f"♟️ *Initiative created:* {initiative.title}\n"
                f"Category: {initiative.category.value.title()} "
                f"| Score: {initiative.scores.total}/25 "
                f"| Visibility: {initiative.visibility.value}"
            ),
        }

    async def _handle_stakeholder(self, text: str) -> dict:
        """Handle /brain stakeholder "Name" [role] — track a new stakeholder.

        Examples:
            /brain stakeholder "Alice Chen" Engineering Manager
            /brain stakeholder "Bob Smith"
        """
        if not text.strip():
            return {
                "response_type": "ephemeral",
                "text": (
                    "Usage: `/brain stakeholder \"Name\" [role]`\n"
                    "Tracks a new stakeholder with default scores. "
                    "Use the web UI to adjust influence, alignment, etc."
                ),
            }

        if not self.strategy_repo:
            return {"response_type": "ephemeral", "text": "Strategy service not available."}

        from src.models.strategy import Stakeholder

        name, role = self._parse_quoted_title(text)

        stakeholder = Stakeholder(name=name, role=role)
        await self.strategy_repo.save_stakeholder(stakeholder)

        role_text = f" ({role})" if role else ""
        return {
            "response_type": "in_channel",
            "text": (
                f"👤 *Stakeholder tracked:* {stakeholder.name}{role_text}\n"
                f"Influence: {stakeholder.influence_level}/10 "
                f"| Alignment: {stakeholder.alignment_score:+d} "
                f"| Trust: {stakeholder.trust_score}/10"
            ),
        }

    async def _handle_asset(self, text: str) -> dict:
        """Handle /brain asset "Title" [reputation|optionality] [description].

        Examples:
            /brain asset "Open Source Project" reputation Key OSS contribution
            /brain asset "Cloud Cert" optionality AWS certification
            /brain asset "Blog Series" Great technical blog
        """
        if not text.strip():
            return {
                "response_type": "ephemeral",
                "text": (
                    "Usage: `/brain asset \"Title\" [reputation|optionality] [description]`\n"
                    "Tracks a strategic asset. Type defaults to reputation."
                ),
            }

        if not self.strategy_repo:
            return {"response_type": "ephemeral", "text": "Strategy service not available."}

        from src.models.strategy import StrategicAsset

        title, remainder = self._parse_quoted_title(text)

        # Parse optional asset type
        asset_type = AssetCategory.REPUTATION
        description = remainder
        if remainder:
            first_word = remainder.split(maxsplit=1)[0].lower()
            if first_word in ("reputation", "optionality"):
                asset_type = AssetCategory(first_word)
                description = remainder.split(maxsplit=1)[1] if len(remainder.split(maxsplit=1)) > 1 else ""

        asset = StrategicAsset(
            title=title,
            description=description,
            asset_type=asset_type,
        )
        await self.strategy_repo.save_asset(asset)

        type_emoji = "🏆" if asset_type == AssetCategory.REPUTATION else "🚪"
        return {
            "response_type": "in_channel",
            "text": (
                f"{type_emoji} *Asset tracked:* {asset.title}\n"
                f"Type: {asset_type.value.title()}"
                + (f"\n_{description[:200]}_" if description else "")
            ),
        }

    @staticmethod
    def _help_response() -> dict:
        """Return help text listing all available commands."""
        return {
            "response_type": "ephemeral",
            "text": (
                "🧠 *Second Brain Commands*\n\n"
                "*Knowledge*\n"
                "• `/brain capture <text>` — Capture and classify a thought\n"
                "• `/brain recall <query>` — Search your knowledge base\n"
                "• `/brain entity <name>` — View entity brief and linked entries\n"
                "• `/brain summarize <name>` — Generate summary for an entity\n\n"
                "*Strategy*\n"
                "• `/brain initiative \"Title\" [description]` — Create a scored initiative\n"
                "• `/brain stakeholder \"Name\" [role]` — Track a stakeholder\n"
                "• `/brain asset \"Title\" [reputation|optionality] [desc]` — Track an asset\n\n"
                "• `/brain help` — Show this help message"
            ),
        }
