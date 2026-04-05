"""Stats routes — core stats only. Premium stats (influencers, content) in ghost_premium."""

from fastapi import APIRouter

router = APIRouter(tags=["stats"])


@router.get("/api/stats", summary="Get Dashboard Stats")
def stats():
    """Dashboard stats. Premium plugin extends this with influencer/content data."""
    return {"premium": False}
