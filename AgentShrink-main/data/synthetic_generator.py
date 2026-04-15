"""
data/synthetic_generator.py
============================
PHASE 2 — Synthetic Data Generator

WHY THIS EXISTS:
  HDBSCAN has parameters (min_cluster_size, min_samples) that need
  tuning. But you can only validate tuning if you KNOW the correct
  answer. With real logs, you don't know the ground truth.

  Synthetic data solves this: we create 100 prompts across 5 known
  task types (we control the labels), run clustering, and check if
  HDBSCAN correctly recovers those 5 clusters. Once it does → our
  parameters are correctly tuned → apply to real data with confidence.

WHAT IT GENERATES:
  5 task clusters × 20 examples each = 100 total synthetic log entries.
  Each entry looks exactly like a real captured log row — same schema,
  same structure. The only difference: we know the correct cluster.

RUN WITH:
  python data/synthetic_generator.py
  → Creates data/synthetic_logs.json
  → Prints a summary of what was generated
"""

import json
import uuid
import random
import pathlib
from datetime import datetime, timezone, timedelta

# ─────────────────────────────────────────────
# THE 5 TASK CLUSTERS + THEIR PROMPT TEMPLATES
#
# These are realistic versions of what a customer
# support agent actually sends to the LLM.
# Each cluster has distinct linguistic patterns —
# which is what sentence-transformers will detect.
# ─────────────────────────────────────────────

SYNTHETIC_CLUSTERS = {

    "classify_complaint": {
        "description": "Classify the type of customer complaint",
        "expected_label": 0,
        "color": "#1D9E75",
        "prompts": [
            "Classify this customer message into one of: refund, shipping, product, other. Message: 'My item arrived broken and I want my money back'",
            "What type of complaint is this? refund/shipping/product/other: 'The package never arrived at my address'",
            "Categorise this support request. Categories: refund, shipping, product, other. Request: 'Wrong size was sent to me'",
            "Identify the complaint category (refund/shipping/product/other): 'Delivery was 3 weeks late'",
            "What is the nature of this complaint: 'The product stopped working after one day of use'",
            "Classify complaint type for: 'I ordered blue but received red'",
            "Determine category (refund/shipping/product/other): 'Item description did not match what I received'",
            "Label this support ticket: 'My package is stuck in transit for 2 weeks'",
            "What category does this fall under: 'Product quality is very poor compared to photos'",
            "Classify: 'Charged twice for the same order, need refund'",
            "Support ticket classification — what type: 'Tracking shows delivered but not received'",
            "Sort this complaint: 'Return requested within 7 days of purchase'",
            "Category for: 'Item damaged during shipping per delivery note'",
            "Classify this message type: 'Requesting cancellation and full refund'",
            "What department should handle: 'Shipment delayed beyond estimated date'",
            "Identify complaint: 'Product does not match specifications listed'",
            "Type of request: 'Package lost by courier according to tracking'",
            "Categorise: 'Defective product received, want exchange or refund'",
            "What is this about: 'Never received order confirmation email'",
            "Complaint type: 'Item arrived with missing accessories'"
        ]
    },

    "extract_order_id": {
        "description": "Extract order ID or reference number from message",
        "expected_label": 1,
        "color": "#7F77DD",
        "prompts": [
            "Extract the order ID from this message. Return only the ID or NOT_FOUND: 'Hi, my order ORD-10021 has not arrived'",
            "Find the order number in: 'I need help with order #45823 placed last week'",
            "What is the order reference in: 'My purchase from Tuesday, reference ORDER-9982, is missing'",
            "Extract order ID: 'Tracking for ORD10045 shows it is stuck in Mumbai'",
            "Pull the order number from: 'Can you check status of my order number 77291?'",
            "Find reference number in: 'Issue with order ref: SO-2024-8812'",
            "Extract order identifier: 'My booking ID is BK-5541 and I need a refund'",
            "Order ID extraction task: 'Problem with ORD-00231 received yesterday'",
            "Get the order number: 'Hi, regarding order 19283 placed on your website'",
            "Extract from text: 'Order confirmation was RCT-44129 from last Monday'",
            "Find purchase ID in: 'My invoice number is INV-2024-3391 and item is wrong'",
            "Extract reference: 'Case about order #ORD88771 delivered damaged'",
            "What order ID appears here: 'Shipment ORD-55102 tracking not updating'",
            "Pull reference number: 'Transaction ID 9928471 was doubled charged'",
            "Find the ID: 'My purchase reference is P-20241109-4421'",
            "Extract: 'Order placed with ID: ORD2024-11-8821'",
            "Order reference in: 'Problem with my recent order, number 556788'",
            "Find order number: 'Complaint about ORD-10089, received wrong color'",
            "Extract ID: 'My case number from last week is CS-4421-2024'",
            "Reference extraction: 'Tracking ORD-10102 shows no movement since Tuesday'"
        ]
    },

    "check_policy": {
        "description": "Apply business rules to determine if request is approved",
        "expected_label": 2,
        "color": "#EF9F27",
        "prompts": [
            "Apply our return policy and respond with approved/denied/needs_review. Situation: customer received damaged item from shipping, order placed 3 days ago",
            "Policy decision required: customer wants refund for digital download purchased yesterday. Apply rules: approved/denied/needs_review",
            "Does this qualify for a refund under our 7-day policy? Customer changed mind 5 days after purchase. Answer: approved/denied/needs_review",
            "Policy check: item marked as final sale, customer requesting return. What is the verdict?",
            "Evaluate refund eligibility: wrong item was delivered, customer reported within 24 hours. Apply policy.",
            "Should we approve this return request: item stopped working after 2 days of normal use?",
            "Policy evaluation: package lost in transit, carrier confirmed lost shipment. Approve refund?",
            "Apply return rules: customer requesting exchange for size, 10 days since purchase (policy: 7 days)",
            "Refund policy assessment: product quality does not match website description. Customer complaint valid?",
            "Determine resolution: item arrived with missing parts, customer wants full refund not replacement",
            "Policy rule application: delayed delivery beyond 14-day SLA, customer demands compensation",
            "Evaluate eligibility: subscription service cancelled within free trial period, no charge yet",
            "Should this be escalated or resolved: customer threatening chargeback for undelivered item?",
            "Policy decision for: customer claims allergic reaction to product, wants immediate refund",
            "Assess return request: gift purchase, recipient doesn't want it, 3 weeks since purchase",
            "Policy check: bulk order partially damaged, customer wants full order refund not partial",
            "Evaluate: second-time customer reporting same defect on replacement item sent last month",
            "Apply refund policy: item sold at clearance price, customer wants to return",
            "Policy assessment: customer claims item never worked from day one, no proof provided",
            "Determine verdict: international order delayed 30 days, customer wants refund or reship"
        ]
    },

    "draft_reply": {
        "description": "Write empathetic professional customer reply",
        "expected_label": 3,
        "color": "#D85A30",
        "prompts": [
            "Write a warm, professional reply to a customer whose refund has been approved. Order ORD-10021. Keep under 100 words.",
            "Draft an empathetic response to a customer who received the wrong item. Apologise and explain the exchange process.",
            "Compose a professional reply explaining that the return request is denied because the 7-day window has passed. Be respectful.",
            "Write a response to a customer asking about their delayed package. Be reassuring and provide next steps.",
            "Draft a sympathetic message to a customer whose order was lost in transit. Include timeline for resolution.",
            "Write a professional reply acknowledging a damaged item complaint and approving an immediate replacement.",
            "Compose a response to an upset customer who has been waiting 3 weeks for their order.",
            "Draft an apology and resolution email for a customer who received a defective product.",
            "Write a clear, friendly message explaining the refund process steps to a customer.",
            "Compose a reply to a customer whose case needs further review from our specialist team.",
            "Draft a follow-up message for a customer whose replacement shipment has been dispatched.",
            "Write an empathetic response to a customer who is reporting their second issue in a month.",
            "Compose a professional reply to a VIP customer escalating an unresolved complaint.",
            "Draft a clear explanation to a customer about why their return request was partially approved.",
            "Write a warm closing message to a customer whose issue has been fully resolved.",
            "Compose a reply to a customer requesting an update on their open support ticket.",
            "Draft a professional response explaining our policy on digital product refunds.",
            "Write an empathetic message to a customer who is frustrated about shipping delays.",
            "Compose a resolution email for a customer dispute that has been escalated to management.",
            "Draft a professional reply to a customer who left a negative review due to delivery issues."
        ]
    },

    "format_output": {
        "description": "Format data into structured JSON output",
        "expected_label": 4,
        "color": "#185FA5",
        "prompts": [
            "Format as JSON with fields order_id, complaint_type, resolution, reply, escalate: order ORD-10021, refund, approved, 'We have approved...', false",
            "Convert to structured JSON output: {order_id: ORD-888, type: shipping, verdict: needs_review, message: 'We are looking...', escalate: true}",
            "Output as valid JSON only — no markdown: order=ORD-445, category=product, status=denied, response='Unfortunately...', needs_escalation=false",
            "Format this support response as JSON with schema {order_id, complaint_type, resolution, reply, escalate}",
            "Structure as JSON: customer order ORD-2291, complaint type refund, resolution approved, draft reply provided, no escalation needed",
            "Convert support ticket data to JSON format: ticket #ORD-9981, type=shipping delay, verdict=approved for reship, reply drafted, no escalation",
            "JSON output required. Fields: order_id, complaint_type, resolution, reply, escalate. Data: ORD-10045, shipping, needs_review, 'We are checking...', true",
            "Format as structured JSON for database insertion: case ORD-77821, complaint category product defect, approved for replacement, response written",
            "Output JSON only: {order: 'ORD-33421', type: 'refund', decision: 'denied', message: 'As per policy...', escalate: false}",
            "Create JSON structure from: ticket ORD-10089 is about wrong item shipped, approved for exchange, reply drafted, no escalation",
            "Structure this as valid JSON: support case ORD-55102 shipping delay complaint, resolution pending, message sent, flagged for review",
            "JSON format for: order ORD-22891 damaged product complaint, refund approved, apology reply written, no escalation required",
            "Convert to JSON schema {order_id, complaint_type, resolution, reply, escalate}: ORD-10102 digital product complaint denied no refund",
            "Format output as JSON for CRM system: reference ORD-4421 refund case approved within policy, customer notified, close ticket",
            "Structured JSON output: case ORD-8812 product quality complaint, needs manager review, holding reply, escalate to tier 2",
            "JSON only response for: ORD-19283 lost package approved for full refund, customer reply drafted, no further escalation",
            "Format for database: order ORD-10034, complaint type damaged item, resolution full refund approved, response prepared",
            "Output as JSON: ORD-10067 delivery dispute needs_review, preliminary reply sent, escalate to shipping partner",
            "Create JSON: support ticket ORD-10078 product defect approved replacement, warm reply drafted, no escalation",
            "JSON structure: case ORD-10091 wrong item shipped approved exchange, apology message ready, no escalation needed"
        ]
    }
}


def generate_synthetic_logs(
    output_path: pathlib.Path = pathlib.Path("data/synthetic_logs.json"),
    seed: int = 42
) -> list[dict]:
    """
    Generate 100 synthetic log entries (20 per cluster).

    Each entry has the same schema as a real captured log row
    from AgentShrinkLogger — this lets us test the clustering
    pipeline on known data before running on real logs.

    Returns the list of generated entries (also saves to JSON).
    """
    random.seed(seed)

    entries = []
    base_time = datetime.now(timezone.utc) - timedelta(days=3)

    cluster_names = list(SYNTHETIC_CLUSTERS.keys())

    for cluster_name, cluster_info in SYNTHETIC_CLUSTERS.items():
        for i, prompt in enumerate(cluster_info["prompts"]):

            # Simulate realistic token counts per task type
            tokens_in = random.randint(50, 200)
            tokens_out = {
                "classify_complaint":  random.randint(1, 5),    # One word output
                "extract_order_id":    random.randint(1, 10),   # Short ID or NOT_FOUND
                "check_policy":        random.randint(1, 5),    # One word verdict
                "draft_reply":         random.randint(60, 120), # Paragraph
                "format_output":       random.randint(40, 80),  # JSON blob
            }[cluster_name]

            # Simulate realistic latency per task type
            latency_ms = {
                "classify_complaint":  random.randint(300, 800),
                "extract_order_id":    random.randint(250, 700),
                "check_policy":        random.randint(400, 900),
                "draft_reply":         random.randint(800, 2500),
                "format_output":       random.randint(350, 900),
            }[cluster_name]

            # Simulate responses that match the task type
            responses = {
                "classify_complaint":  random.choice(["refund", "shipping", "product", "other"]),
                "extract_order_id":    f"ORD-{random.randint(10000, 99999)}",
                "check_policy":        random.choice(["approved", "denied", "needs_review"]),
                "draft_reply":         "Dear valued customer, thank you for reaching out to us...",
                "format_output":       '{"order_id": "ORD-12345", "complaint_type": "refund", "resolution": "approved"}',
            }[cluster_name]

            entry = {
                # Identity
                "call_id":     str(uuid.uuid4()),
                "run_id":      str(uuid.uuid4()),  # Each synthetic entry is its own "run"

                # Timing
                "timestamp":   (base_time + timedelta(seconds=i * 30)).isoformat(),
                "latency_ms":  latency_ms,

                # Content
                "prompt":      prompt,
                "response":    responses,
                "prompt_hash": None,  # Will be computed by clusterer

                # Model info
                "model_name":  "gpt-4o-mini",
                "node_name":   cluster_name,  # Ground truth label (not used in clustering)

                # Tokens
                "tokens_in":   tokens_in,
                "tokens_out":  tokens_out,
                "cost_usd":    round((tokens_in * 0.00015 + tokens_out * 0.0006) / 1000, 6),

                # Clustering (ground truth — for validation only)
                "cluster_id":         -1,         # Not clustered yet
                "true_cluster_id":    cluster_info["expected_label"],  # Ground truth
                "true_cluster_name":  cluster_name,                    # Ground truth

                # Quality
                "workflow_success": 1,
                "extra_metadata": "{}",
            }
            entries.append(entry)

    # Shuffle so clusters aren't in order (more realistic)
    random.shuffle(entries)

    # Save to JSON
    output_path = pathlib.Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(entries, f, indent=2)

    return entries


if __name__ == "__main__":
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich import box

    console = Console()

    console.print(Panel.fit(
        "[bold]Synthetic Data Generator[/bold]\n"
        "Generating 100 labelled prompt examples\n"
        "across 5 known task clusters.",
        border_style="blue"
    ))

    entries = generate_synthetic_logs()

    # Show summary
    table = Table(title="Generated Clusters", box=box.ROUNDED)
    table.add_column("Cluster",     style="white")
    table.add_column("Examples",    justify="right", style="cyan")
    table.add_column("Sample prompt",               style="dim")

    cluster_counts = {}
    cluster_samples = {}
    for e in entries:
        name = e["true_cluster_name"]
        cluster_counts[name] = cluster_counts.get(name, 0) + 1
        cluster_samples[name] = e["prompt"][:55] + "..."

    for name, count in sorted(cluster_counts.items()):
        table.add_row(name, str(count), cluster_samples[name])

    console.print(table)
    console.print(f"\n  [green]✓ Saved to data/synthetic_logs.json[/green]")
    console.print(f"  Total entries: {len(entries)}")
    console.print(f"\n  Next: run tests/test_phase2_clustering.py to validate clustering on this data.")
