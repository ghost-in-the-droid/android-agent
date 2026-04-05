"""TikTok Upload Video workflow — wraps the existing upload bot logic."""
from gitd.skills.base import Workflow, Action, ActionResult
import logging

log = logging.getLogger(__name__)


class UploadVideoAction(Action):
    """Delegates to the existing upload.py logic."""
    name = 'upload_video_action'
    description = 'Upload a video to TikTok with caption and hashtags'

    def __init__(self, device, elements, *, video_path: str = '', caption: str = '',
                 hashtags: str = '', as_draft: bool = False, **kwargs):
        super().__init__(device, elements)
        self.video_path = video_path
        self.caption = caption
        self.hashtags = hashtags
        self.as_draft = as_draft

    def execute(self) -> ActionResult:
        try:
            from gitd.bots.tiktok.upload import upload_video
            result = upload_video(
                self.device, self.video_path,
                caption=self.caption, hashtags=self.hashtags,
                as_draft=self.as_draft,
            )
            return ActionResult(success=bool(result), data={"result": str(result)})
        except ImportError:
            return ActionResult(success=False, error="upload module not available — run via bot subprocess")
        except Exception as e:
            return ActionResult(success=False, error=str(e))


class UploadVideo(Workflow):
    name = 'upload_video'
    description = 'Upload a video to TikTok with caption and hashtags'

    def __init__(self, device, elements, *, video_path: str = '', caption: str = '',
                 hashtags: str = '', as_draft: bool = False, **kwargs):
        super().__init__(device, elements)
        self.video_path = video_path
        self.caption = caption
        self.hashtags = hashtags
        self.as_draft = as_draft

    def steps(self) -> list[Action]:
        return [
            UploadVideoAction(
                self.device, self.elements,
                video_path=self.video_path,
                caption=self.caption,
                hashtags=self.hashtags,
                as_draft=self.as_draft,
            ),
        ]
