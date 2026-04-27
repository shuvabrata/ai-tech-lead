"""Registry for out-of-the-box analytics visualizations.

This module is the single source of truth for graph-based analytics that can be
launched from the Analytics gallery and rendered in the generic graph page.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class GraphAnalytic:
    """Metadata for a pre-built graph analytic."""

    key: str
    title: str
    description: str
    icon: str

    @property
    def href(self) -> str:
        """Return the graph-page route used to launch this analytic."""
        return f"/app/graph?mode={self.key}"


COLLABORATION_NETWORK_ANALYTIC = GraphAnalytic(
    key="collaboration_network",
    title="Collaboration Network",
    description=(
        "Discover organic teams and collaboration hubs from GitHub and Jira "
        "interactions over the last 90 days."
    ),
    icon="fas fa-share-nodes",
)


GRAPH_ANALYTICS = [
    COLLABORATION_NETWORK_ANALYTIC,
]


GRAPH_ANALYTICS_BY_KEY = {analytic.key: analytic for analytic in GRAPH_ANALYTICS}
