from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .wft import WftFragment


class WftIssueSeverity(StrEnum):
    ERROR = "error"
    WARNING = "warning"


@dataclass(frozen=True, slots=True)
class WftValidationIssue:
    code: str
    message: str
    severity: WftIssueSeverity = WftIssueSeverity.ERROR
    group_index: int | None = None
    child_index: int | None = None

    def to_data(self) -> dict[str, object]:
        return {
            "code": self.code,
            "message": self.message,
            "severity": self.severity.value,
            "group_index": self.group_index,
            "child_index": self.child_index,
        }


def validate_wft_fragment(
    fragment: WftFragment,
) -> tuple[WftValidationIssue, ...]:
    """Return structural issues without decoding lazy child drawables."""

    issues: list[WftValidationIssue] = []

    def add(
        code: str,
        message: str,
        *,
        severity: WftIssueSeverity = WftIssueSeverity.ERROR,
        group_index: int | None = None,
        child_index: int | None = None,
    ) -> None:
        issues.append(WftValidationIssue(
            code,
            message,
            severity,
            group_index,
            child_index,
        ))

    group_count = len(fragment.groups)
    child_count = len(fragment.children)
    child_groups_by_parent: list[list[int]] = [
        [] for _ in fragment.groups
    ]
    for index, group in enumerate(fragment.groups):
        if (
            group.parent_group_index != 0xFF
            and group.parent_group_index < group_count
        ):
            child_groups_by_parent[group.parent_group_index].append(index)
    if fragment.root_group_count != len(fragment.root_groups):
        add(
            "root_group_count_mismatch",
            f"declared {fragment.root_group_count} root groups but found "
            f"{len(fragment.root_groups)}",
        )
    if child_count and fragment.root_child_index >= child_count:
        add(
            "root_child_out_of_range",
            f"root child index {fragment.root_child_index} exceeds "
            f"{child_count} children",
        )
    if fragment.bony_child_count > child_count:
        add(
            "bony_child_count_out_of_range",
            f"declared {fragment.bony_child_count} bony children but only "
            f"{child_count} children exist",
        )
    for name, values in (
        ("child_inertia", fragment.child_inertia),
        ("damaged_child_inertia", fragment.damaged_child_inertia),
        ("child_matrices", fragment.child_matrices),
    ):
        if len(values) not in (0, child_count):
            add(
                f"{name}_count_mismatch",
                f"{name} has {len(values)} entries for {child_count} children",
            )
    if (
        fragment.damaged_drawable_index != -1
        and not 0 <= fragment.damaged_drawable_index < len(fragment.extra_drawables)
    ):
        add(
            "damaged_drawable_index_out_of_range",
            f"damaged drawable index {fragment.damaged_drawable_index} exceeds "
            f"{len(fragment.extra_drawables)} extra drawables",
        )
    if len(fragment.extra_drawable_names) != len(fragment.extra_drawables):
        add(
            "extra_drawable_name_count_mismatch",
            f"{len(fragment.extra_drawable_names)} names describe "
            f"{len(fragment.extra_drawables)} extra drawables",
        )

    for child_index, child in enumerate(fragment.children):
        if child.group_index >= group_count:
            add(
                "child_group_out_of_range",
                f"child references missing group {child.group_index}",
                child_index=child_index,
            )

    for group_index, group in enumerate(fragment.groups):
        parent_index = group.parent_group_index
        if parent_index == group_index:
            add(
                "group_self_parent",
                "group identifies itself as its parent",
                group_index=group_index,
            )
        elif parent_index != 0xFF and parent_index >= group_count:
            add(
                "group_parent_out_of_range",
                f"parent group index {parent_index} exceeds {group_count} groups",
                group_index=group_index,
            )

        child_end = group.child_index + group.child_count
        if child_end > child_count:
            add(
                "group_child_range_out_of_range",
                f"child range [{group.child_index}, {child_end}) exceeds "
                f"{child_count} children",
                group_index=group_index,
            )
        else:
            for child_index in range(group.child_index, child_end):
                if fragment.children[child_index].group_index != group_index:
                    add(
                        "group_child_membership_mismatch",
                        f"child {child_index} belongs to group "
                        f"{fragment.children[child_index].group_index}",
                        group_index=group_index,
                        child_index=child_index,
                    )

        child_group_end = group.child_group_index + group.child_group_count
        actual = tuple(child_groups_by_parent[group_index])
        if group.child_group_count and child_group_end > group_count:
            add(
                "group_child_group_range_out_of_range",
                f"child-group range [{group.child_group_index}, "
                f"{child_group_end}) exceeds {group_count} groups",
                group_index=group_index,
            )
        else:
            declared = (
                ()
                if group.child_group_count == 0
                else tuple(range(group.child_group_index, child_group_end))
            )
            if declared != actual:
                add(
                    "group_child_group_layout_mismatch",
                    f"declared child groups {declared}, found {actual}",
                    group_index=group_index,
                )

    completed: set[int] = set()
    for start in range(group_count):
        if start in completed:
            continue
        path: list[int] = []
        positions: dict[int, int] = {}
        current = start
        while (
            current != 0xFF
            and current < group_count
            and current not in completed
            and current not in positions
        ):
            positions[current] = len(path)
            path.append(current)
            current = fragment.groups[current].parent_group_index
        if current in positions:
            for group_index in path[positions[current]:]:
                add(
                    "group_hierarchy_cycle",
                    f"parent chain repeats group {current}",
                    group_index=group_index,
                )
        completed.update(path)

    for index, collision in enumerate(fragment.self_collisions):
        if collision.first >= child_count or collision.second >= child_count:
            add(
                "self_collision_child_out_of_range",
                f"self-collision {index} references children "
                f"{collision.first} and {collision.second}",
            )
    return tuple(issues)


__all__ = [
    "WftIssueSeverity",
    "WftValidationIssue",
    "validate_wft_fragment",
]
