"""
Purpose-built prompt generator for the in-product fine-tune demo.

This keeps the current customer-support agent, but gives us a much larger and
more controlled prompt set so the dashboard reliably produces:
- obvious replace-now clusters for classify/extract/format
- a policy-heavy fine-tune candidate for check_policy_node
- a keep-on-fallback cluster for draft_reply_node
"""

from __future__ import annotations

from itertools import cycle


SCENARIO_TEMPLATES = [
    {
        "label": "damaged",
        "template": "My {item} from order {order_id} arrived damaged. The {damage_detail}. Please tell me if policy allows a refund or replacement.",
    },
    {
        "label": "wrong_item",
        "template": "I ordered {expected_item} in order {order_id} but received {wrong_item}. What does policy say about refunding this?",
    },
    {
        "label": "changed_mind_in_window",
        "template": "I changed my mind about order {order_id} after {days} days. It is still unused. Can policy approve a return?",
    },
    {
        "label": "changed_mind_late",
        "template": "Order {order_id} was delivered {days} days ago and I no longer want the {item}. Does policy allow a refund now?",
    },
    {
        "label": "digital_product",
        "template": "I purchased digital item {item} on order {order_id}. I do not like it anymore. Can policy approve a refund for digital goods?",
    },
    {
        "label": "delayed_shipping",
        "template": "Shipment for order {order_id} has been delayed for {days} days. What does policy say about refund or reship?",
    },
    {
        "label": "lost_in_transit",
        "template": "Carrier confirmed order {order_id} was lost in transit. What does policy say about refund or reship for my {item}?",
    },
]

ITEMS = [
    "air fryer",
    "blender",
    "gaming mouse",
    "desk lamp",
    "water bottle",
    "headphones",
    "yoga mat",
    "coffee grinder",
]

WRONG_ITEMS = [
    "a black shirt",
    "a smaller backpack",
    "the wrong phone case",
    "a used keyboard",
    "a silver toaster",
]

DAMAGE_DETAILS = [
    "screen is cracked",
    "glass jar is shattered",
    "housing is dented",
    "motor makes a burning smell",
    "box was crushed and parts are missing",
]


def generate_finetune_lab_messages(count: int = 72) -> list[str]:
    messages: list[str] = []
    items = cycle(ITEMS)
    wrong_items = cycle(WRONG_ITEMS)
    damage_details = cycle(DAMAGE_DETAILS)

    for idx in range(count):
        scenario = SCENARIO_TEMPLATES[idx % len(SCENARIO_TEMPLATES)]
        order_id = f"ORD-{32000 + idx:05d}"
        item = next(items)
        expected_item = f"{item} bundle"
        wrong_item = next(wrong_items)
        damage_detail = next(damage_details)
        days = 3 + (idx % 18)

        messages.append(
            scenario["template"].format(
                order_id=order_id,
                item=item,
                expected_item=expected_item,
                wrong_item=wrong_item,
                damage_detail=damage_detail,
                days=days,
            )
        )

    return messages


LAB_VERIFICATION_MESSAGES = [
    "Carrier confirmed order ORD-41001 was lost in transit. What does policy say about refund or reship for my blender?",
    "I changed my mind about order ORD-41002 after 5 days. It is still unused. Can policy approve a return?",
    "I purchased digital item video-course on order ORD-41003. I do not like it anymore. Can policy approve a refund for digital goods?",
    "My air fryer from order ORD-41004 arrived damaged. The screen is cracked. Please tell me if policy allows a refund or replacement.",
]
