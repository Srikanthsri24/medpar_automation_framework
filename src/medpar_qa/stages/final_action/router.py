"""Select the first applicable rule in explicit decision-tree order. Specific rules precede general
fallbacks.
"""
from __future__ import annotations

from .context import FinalActionGroupContext
from .rules import (
    AllQC0Rule,
    DefaultFinalActionRule,
    Rule01SingleClaim,
    Rule02ThreeClaimSequence,
    Rule03SameQueryCode,
    Rule05ThreeClaimsOneQC0NoQC5,
    Rule06TwoClaimsQC0QC5,
    Rule07NoQC5QC0Dominates,
    Rule08NoQC5LatestQC0,
    Rule09NoQC5LatestNonQC0,
    Rule10AQC5QC0Dominates,
    Rule10BQC5Fallback,
)
from .rules.base import FinalActionRule
from .settings import FinalActionSettings


class FinalActionRuleRouter:
    """Select exactly one rule using the approved decision-tree precedence."""

    def __init__(self, settings: FinalActionSettings) -> None:
        """Initialize this FinalActionRuleRouter with the supplied dependencies/configuration and
        the assignments in its constructor.
        """
        self.rules: tuple[FinalActionRule, ...] = (
            AllQC0Rule(),
            Rule01SingleClaim(settings),
            Rule02ThreeClaimSequence(settings),
            Rule06TwoClaimsQC0QC5(settings),
            Rule05ThreeClaimsOneQC0NoQC5(),
            Rule03SameQueryCode(),
            Rule10AQC5QC0Dominates(settings),
            Rule10BQC5Fallback(settings),
            Rule07NoQC5QC0Dominates(),
            Rule08NoQC5LatestQC0(),
            Rule09NoQC5LatestNonQC0(),
            DefaultFinalActionRule(),
        )

    def select(self, context: FinalActionGroupContext) -> FinalActionRule:
        """Return the first applicable rule in the router precedence; the default ensures an
        unmatched group is explicitly blocked.
        """
        matches = [rule for rule in self.rules if rule.applies(context)]
        # Default always matches, therefore the first match is the selected route.
        return matches[0]
