"""Grounding validator — checks that every recommendation is grounded in menu data."""
import re


def validate(
    recommendations,  # list[Recommendation]
    picks: list[dict],
    reply: str,
) -> tuple[bool, list[str]]:
    """Validate that recommendations are grounded.

    Checks:
    1. Every item_id in recommendations is in picks.
    2. Every cited_field is a real field in the menu item.
    3. Numbers mentioned in the reason match the actual menu field value.

    Returns (ok, errors).
    """
    pick_by_id = {item["id"]: item for item in picks}
    errors: list[str] = []

    for rec in recommendations:
        iid = rec.item_id
        if iid not in pick_by_id:
            errors.append(f"item_id {iid!r} is not in picks")
            continue

        item = pick_by_id[iid]

        # cited_fields exist
        for field in rec.cited_fields:
            if field not in item:
                errors.append(f"{iid}: cited_field {field!r} not in menu item")

        # Numbers in reason match menu values for cited numeric fields
        numeric_fields = {"price_inr", "prep_time_min", "spice_level", "serves"}
        for field in rec.cited_fields:
            if field in numeric_fields and field in item:
                actual = item[field]
                # Find all numbers in the reason text
                nums_in_reason = re.findall(r"\d+", rec.reason)
                if nums_in_reason and str(actual) not in nums_in_reason:
                    # Only flag if there are numbers and none match
                    errors.append(
                        f"{iid}: reason mentions {nums_in_reason} but {field}={actual}"
                    )

    return len(errors) == 0, errors

