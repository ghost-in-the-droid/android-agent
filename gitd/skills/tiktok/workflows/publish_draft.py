"""TikTok Publish Draft workflow — publishes a saved draft."""
from gitd.skills.base import Workflow, Action, ActionResult


class PublishDraftAction(Action):
    name = 'publish_draft_action'
    description = 'Open drafts and publish the first matching draft'

    def __init__(self, device, elements, *, draft_tag: str = '', **kwargs):
        super().__init__(device, elements)
        self.draft_tag = draft_tag

    def execute(self) -> ActionResult:
        try:
            from gitd.bots.tiktok.upload import publish_draft
            result = publish_draft(self.device, draft_tag=self.draft_tag)
            return ActionResult(success=bool(result), data={"result": str(result)})
        except ImportError:
            return ActionResult(success=False, error="upload module not available")
        except Exception as e:
            return ActionResult(success=False, error=str(e))


class PublishDraft(Workflow):
    name = 'publish_draft'
    description = 'Open drafts and publish a saved draft'

    def __init__(self, device, elements, *, draft_tag: str = '', **kwargs):
        super().__init__(device, elements)
        self.draft_tag = draft_tag

    def steps(self) -> list[Action]:
        return [PublishDraftAction(self.device, self.elements, draft_tag=self.draft_tag)]
