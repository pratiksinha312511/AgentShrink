"""
data/seed_database.py
=====================
Insert 200 realistic synthetic LLM calls into the AgentShrink SQLite DB
so the dashboard clustering, report, and finetune sections have data.

Covers 5 distinct task clusters x 40 calls each = 200 total.
Each call has realistic prompts, responses, token counts, and latencies.

Usage:
    python data/seed_database.py
"""

import hashlib
import json
import os
import pathlib
import random
import sqlite3
import uuid
from datetime import datetime, timezone, timedelta

from dotenv import load_dotenv

load_dotenv()

DB_PATH = pathlib.Path(
    os.getenv("AGENTSHRINK_DB_PATH", "~/.agentshrink/logs.db")
).expanduser()

# ── 5 Task Clusters with 40 diverse prompts each ──────────────────────

CLUSTERS = {
    "classify_complaint": {
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
            "Complaint type: 'Item arrived with missing accessories'",
            "Classify the support ticket: 'Order arrived but box was completely crushed'",
            "What kind of issue: 'Wrong product variant shipped to customer'",
            "Determine complaint type: 'Customer unhappy with product material quality'",
            "Classification: 'Haven't received tracking update in 10 days'",
            "Sort ticket into category: 'Requesting full refund after poor experience'",
            "What type: 'My subscription was charged after I cancelled it'",
            "Classify: 'Received expired product, requesting immediate replacement'",
            "Category determination: 'Warehouse shipped the wrong quantity of items'",
            "Ticket type: 'Product arrived with scratches and dents on surface'",
            "Classify this issue: 'Courier left package in the rain, items damaged'",
            "Complaint category for: 'Waiting 5 weeks for international shipment'",
            "Type: 'App shows order delivered but nothing at my door'",
            "What kind: 'Product safety concern — sharp edges on children toy'",
            "Classify: 'Billed for premium plan but only have basic access'",
            "Category: 'Return label not working, cannot process my return'",
            "Sort: 'Gift card balance disappeared from my account'",
            "Determine: 'Promotion code was not applied at checkout'",
            "Classify this: 'Delivery person left package at wrong house number'",
            "Type of issue: 'Product color different from what shown on website'",
            "Classify: 'Received someone else order instead of mine'",
        ],
        "responses": ["refund", "shipping", "product", "other"],
        "tokens_out_range": (1, 5),
        "latency_range": (200, 800),
    },
    "extract_order_id": {
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
            "Reference extraction: 'Tracking ORD-10102 shows no movement since Tuesday'",
            "Extract the order ID: 'Following up on order ORD-30291 from March'",
            "Find the reference: 'Need status update for purchase PO-88712'",
            "Order number in: 'My recent order ORD-44552 was charged incorrectly'",
            "Extract: 'Help needed with booking reference BR-90123'",
            "Pull order ID: 'Regarding invoice INV-77821 issued last Friday'",
            "Find ID: 'Tracking number TRK-55098 shows package returned to sender'",
            "Extract reference from: 'My order ORD-66234 has been delayed 3 times now'",
            "What order number: 'Subscription ID SUB-2024-4489 needs cancellation'",
            "Find purchase reference: 'Warranty claim for order WR-12098'",
            "Extract: 'Case file REF-80091-X opened about my missing delivery'",
            "Order ID: 'My receipt shows order number ORD-91827 from your store'",
            "Find the ID in: 'I placed order ORD-73345 and got wrong items'",
            "Extract order: 'Return request for purchase #ORD-82917'",
            "Pull reference: 'Gift order GO-55412 sent to wrong address'",
            "Order number extraction: 'My membership order is MEM-2024-9921'",
            "Find: 'Need update on bulk order BO-18234 placed two weeks ago'",
            "Extract the reference number: 'Support ticket linked to order ORD-40091'",
            "What is the order: 'Exchange request for ORD-61129 wrong size'",
            "Find purchase ID: 'My pre-order PRE-33445 release date query'",
            "Extract: 'Complaint escalated about order ORD-50018 by supervisor'",
        ],
        "responses": [f"ORD-{i}" for i in range(10000, 10040)],
        "tokens_out_range": (1, 10),
        "latency_range": (200, 700),
    },
    "check_policy": {
        "prompts": [
            "Apply our return policy and respond with approved/denied/needs_review. Situation: customer received damaged item, order placed 3 days ago",
            "Policy decision required: customer wants refund for digital download purchased yesterday. Apply rules.",
            "Does this qualify for a refund under our 7-day policy? Customer changed mind 5 days after purchase.",
            "Policy check: item marked as final sale, customer requesting return. What is the verdict?",
            "Evaluate refund eligibility: wrong item was delivered, customer reported within 24 hours.",
            "Should we approve this return request: item stopped working after 2 days of normal use?",
            "Policy evaluation: package lost in transit, carrier confirmed lost shipment. Approve refund?",
            "Apply return rules: customer requesting exchange for size, 10 days since purchase (policy: 7 days)",
            "Refund policy assessment: product quality does not match website description.",
            "Determine resolution: item arrived with missing parts, customer wants full refund not replacement",
            "Policy rule application: delayed delivery beyond 14-day SLA, customer demands compensation",
            "Evaluate eligibility: subscription cancelled within free trial period, no charge yet",
            "Should this be escalated or resolved: customer threatening chargeback for undelivered item?",
            "Policy decision for: customer claims allergic reaction to product, wants immediate refund",
            "Assess return request: gift purchase, recipient doesn't want it, 3 weeks since purchase",
            "Policy check: bulk order partially damaged, customer wants full order refund not partial",
            "Evaluate: second-time customer reporting same defect on replacement item",
            "Apply refund policy: item sold at clearance price, customer wants to return",
            "Policy assessment: customer claims item never worked from day one, no proof provided",
            "Determine verdict: international order delayed 30 days, customer wants refund or reship",
            "Return policy check: opened electronics product, 5 days old, customer wants refund",
            "Evaluate eligibility: customer bought wrong model, wants exchange within 48 hours",
            "Policy ruling: perishable goods arrived spoiled, customer has photographic evidence",
            "Assess: loyalty program member requesting exception to standard return window",
            "Refund decision: subscription renewed automatically, customer wants cancellation and refund",
            "Policy check: customer received counterfeit product from marketplace seller",
            "Determine: warranty claim for product that failed after 11 months (12-month warranty)",
            "Evaluate: customer disputes delivery signature, claims they were not home",
            "Policy assessment: order placed during promotional period, customer wants price adjustment",
            "Should we approve: customer found cheaper price elsewhere within 7 days of purchase",
            "Evaluate refund: customer accidentally ordered duplicate, noticed before shipping",
            "Policy decision: seasonal item return requested 2 days after return window closed",
            "Assess eligibility: business customer requesting bulk return of 50 units",
            "Apply rules: customer claims product caused minor property damage, requesting compensation",
            "Policy check: product recall issued, customer had already requested return independently",
            "Evaluate: custom-made product that doesn't meet customer specifications",
            "Determine: reseller purchased 100 units at discount, now wants to return 80",
            "Policy ruling: customer found undisclosed defect 3 months after purchase",
            "Assess: customer requesting refund for service subscription unused for 6 months",
            "Evaluate eligibility: item purchased as part of bundle, customer wants partial return",
        ],
        "responses": ["approved", "denied", "needs_review"],
        "tokens_out_range": (1, 5),
        "latency_range": (300, 900),
    },
    "draft_reply": {
        "prompts": [
            "Write a warm, professional reply to a customer whose refund has been approved. Order ORD-10021. Keep under 100 words.",
            "Draft an empathetic response to a customer who received the wrong item. Apologise and explain the exchange process.",
            "Compose a professional reply explaining that the return request is denied because the 7-day window has passed.",
            "Write a response to a customer asking about their delayed package. Be reassuring and provide next steps.",
            "Draft a sympathetic message to a customer whose order was lost in transit. Include timeline for resolution.",
            "Write a professional reply acknowledging a damaged item complaint and approving an immediate replacement.",
            "Compose a response to an upset customer who has been waiting 3 weeks for their order.",
            "Draft an apology and resolution email for a customer who received a defective product.",
            "Write a clear, friendly message explaining the refund process steps to a customer.",
            "Compose a reply to a customer whose case needs further review from our specialist team.",
            "Draft a follow-up message for a customer whose replacement shipment has been dispatched.",
            "Write an empathetic response to a customer reporting their second issue in a month.",
            "Compose a professional reply to a VIP customer escalating an unresolved complaint.",
            "Draft a clear explanation to a customer about why their return was partially approved.",
            "Write a warm closing message to a customer whose issue has been fully resolved.",
            "Compose a reply to a customer requesting an update on their open support ticket.",
            "Draft a professional response explaining our policy on digital product refunds.",
            "Write an empathetic message to a customer frustrated about repeated shipping delays.",
            "Compose a resolution email for a customer dispute escalated to management.",
            "Draft a professional reply to a customer who left a negative review due to delivery issues.",
            "Write a thank-you message to a loyal customer who reported a product issue constructively.",
            "Compose a reply offering store credit as an alternative to a refund for a valued customer.",
            "Draft a message explaining the warranty claim process and expected timeline.",
            "Write a response to a customer asking about their replacement order shipping status.",
            "Compose a professional apology for a billing error and explain the correction steps.",
            "Draft a reply to a customer who wants to upgrade their support ticket priority.",
            "Write a message explaining why a price match request was declined per our policy.",
            "Compose a follow-up email checking customer satisfaction after issue resolution.",
            "Draft a professional notification about a product recall affecting the customer order.",
            "Write a response to a customer requesting a manager callback about their complaint.",
            "Compose a message acknowledging a safety concern and explaining our review process.",
            "Draft a reply to a customer inquiring about compensation for extended delivery delay.",
            "Write a professional message about partial refund approval with detailed breakdown.",
            "Compose a response for a customer asking about order modification after payment.",
            "Draft an email confirming subscription cancellation and explaining any final charges.",
            "Write a warm message to a customer returning after a negative experience.",
            "Compose a reply explaining the difference between refund and store credit options.",
            "Draft a professional response to a customer filing an insurance claim for lost package.",
            "Write a message to a customer about the investigation results for their missing order.",
            "Compose a closing summary email after resolving a complex multi-issue customer case.",
        ],
        "responses": [
            "Dear valued customer, thank you for reaching out. We sincerely apologize for the inconvenience. Your refund has been processed and should appear in your account within 3-5 business days. We appreciate your patience.",
            "We're sorry to hear about your experience. We've initiated a replacement shipment and you should receive your new item within 5-7 business days. A prepaid return label has been emailed to you.",
            "Thank you for contacting us. We understand your frustration and have escalated your case to our specialist team. You'll receive an update within 24 hours.",
            "We appreciate your patience during this process. Your replacement order has been shipped and here is your new tracking number. Please don't hesitate to reach out if you need anything else.",
            "We're truly sorry for the inconvenience caused. After reviewing your case, we've approved a full refund along with a 15% discount code for your next purchase as a gesture of goodwill.",
        ],
        "tokens_out_range": (40, 120),
        "latency_range": (600, 2500),
    },
    "format_output": {
        "prompts": [
            "Format as JSON with fields order_id, complaint_type, resolution, reply, escalate: order ORD-10021, refund, approved",
            "Convert to structured JSON output: order ORD-888, type shipping, verdict needs_review",
            "Output as valid JSON only — no markdown: order=ORD-445, category=product, status=denied",
            "Format this support response as JSON with schema {order_id, complaint_type, resolution, reply, escalate}",
            "Structure as JSON: order ORD-2291, complaint type refund, resolution approved, no escalation",
            "Convert support ticket to JSON format: ticket ORD-9981, type=shipping delay, verdict=approved for reship",
            "JSON output required. Fields: order_id, complaint_type, resolution, reply, escalate. Data: ORD-10045",
            "Format as structured JSON for database: case ORD-77821, complaint product defect, approved replacement",
            "Output JSON only: order ORD-33421, type refund, decision denied",
            "Create JSON structure from: ticket ORD-10089 wrong item shipped, approved for exchange",
            "Structure as valid JSON: support case ORD-55102 shipping delay, resolution pending",
            "JSON format for: order ORD-22891 damaged product, refund approved",
            "Convert to JSON schema: ORD-10102 digital product complaint denied no refund",
            "Format output for CRM system: reference ORD-4421 refund approved within policy",
            "Structured JSON output: case ORD-8812 product quality complaint, needs manager review",
            "JSON only response for: ORD-19283 lost package approved for full refund",
            "Format for database: order ORD-10034, damaged item, full refund approved",
            "Output as JSON: ORD-10067 delivery dispute needs_review",
            "Create JSON: support ticket ORD-10078 product defect, approved replacement",
            "JSON structure: case ORD-10091 wrong item shipped, approved exchange",
            "Format as JSON: ORD-20145, billing error, refund approved, customer notified",
            "Convert to structured output: case ORD-31092, warranty claim, pending review",
            "JSON format required: order ORD-42198, subscription cancellation, processed",
            "Structure as JSON: ticket ORD-53201, product recall, replacement shipped",
            "Output JSON: ORD-64310, size exchange, approved, label sent",
            "Format for API: case ORD-75423, damaged in transit, insurance claim filed",
            "Create JSON response: order ORD-86534, late delivery, compensation offered",
            "Convert to JSON: ticket ORD-97645, wrong quantity, partial refund approved",
            "JSON output: ORD-10876, quality issue, replacement sent, no escalation",
            "Structure as JSON for export: case ORD-11987, payment dispute, resolved",
            "Format output: order ORD-13098, missing items, partial reshipment",
            "JSON format: ORD-14209, allergic reaction claim, escalated to safety team",
            "Convert support data: ticket ORD-15310, duplicate charge, refund processed",
            "Output JSON: ORD-16421, gift return, store credit issued",
            "Create structured JSON: order ORD-17532, international delay, refund offered",
            "Format as JSON: case ORD-18643, bulk order defect, partial replacement",
            "JSON structure: ORD-19754, pre-order cancellation, full refund",
            "Convert to format: ticket ORD-20865, promotion not applied, credit added",
            "Output as structured JSON: order ORD-21976, wrong address delivery, reshipment",
            "Format JSON: case ORD-23087, membership issue, account corrected, no charge",
        ],
        "responses": [
            '{"order_id": "ORD-10021", "complaint_type": "refund", "resolution": "approved", "escalate": false}',
            '{"order_id": "ORD-888", "complaint_type": "shipping", "resolution": "needs_review", "escalate": true}',
            '{"order_id": "ORD-445", "complaint_type": "product", "resolution": "denied", "escalate": false}',
            '{"order_id": "ORD-2291", "complaint_type": "refund", "resolution": "approved", "reply": "Refund processed.", "escalate": false}',
            '{"order_id": "ORD-9981", "complaint_type": "shipping", "resolution": "approved", "reply": "Replacement shipped.", "escalate": false}',
        ],
        "tokens_out_range": (30, 80),
        "latency_range": (300, 900),
    },
}


def seed_database(db_path: pathlib.Path = DB_PATH, count_per_cluster: int = 40) -> int:
    """Insert synthetic calls into the AgentShrink SQLite DB."""
    random.seed(42)

    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS llm_calls (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            call_id     TEXT NOT NULL UNIQUE,
            run_id      TEXT,
            timestamp   TEXT NOT NULL,
            latency_ms  INTEGER,
            prompt      TEXT NOT NULL,
            response    TEXT,
            prompt_hash TEXT,
            model_name  TEXT,
            node_name   TEXT,
            tokens_in   INTEGER DEFAULT 0,
            tokens_out  INTEGER DEFAULT 0,
            cost_usd    REAL DEFAULT 0.0,
            cluster_id  INTEGER DEFAULT -1,
            workflow_success  INTEGER DEFAULT 1,
            extra_metadata TEXT DEFAULT '{}'
        )
    """)

    base_time = datetime.now(timezone.utc) - timedelta(days=7)
    model_name = "moonshotai/kimi-k2-instruct"  # Match the .env TARGET_AGENT_NVIDIA_MODEL
    inserted = 0
    call_index = 0

    for cluster_name, cluster_cfg in CLUSTERS.items():
        prompts = cluster_cfg["prompts"]
        for i in range(count_per_cluster):
            prompt = prompts[i % len(prompts)]
            # Add slight variation for duplicates
            if i >= len(prompts):
                prompt = prompt + f" (variation {i - len(prompts) + 1})"

            response = random.choice(cluster_cfg["responses"])
            tokens_in = random.randint(40, 200)
            tokens_out = random.randint(*cluster_cfg["tokens_out_range"])
            latency_ms = random.randint(*cluster_cfg["latency_range"])
            cost_usd = round((tokens_in * 0.00014 + tokens_out * 0.00056) / 1000, 6)

            call_id = str(uuid.uuid4())
            run_id = f"seed-run-{call_index // 5}"  # Group every 5 calls into a run
            timestamp = (base_time + timedelta(minutes=call_index * 3)).isoformat()
            prompt_hash = hashlib.sha256(prompt.encode()).hexdigest()[:16]

            try:
                conn.execute(
                    """INSERT OR IGNORE INTO llm_calls
                       (call_id, run_id, timestamp, latency_ms, prompt, response,
                        prompt_hash, model_name, node_name, tokens_in, tokens_out,
                        cost_usd, cluster_id, workflow_success, extra_metadata)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (call_id, run_id, timestamp, latency_ms, prompt, response,
                     prompt_hash, model_name, cluster_name, tokens_in, tokens_out,
                     cost_usd, -1, 1, '{}'),
                )
                inserted += 1
            except sqlite3.IntegrityError:
                pass

            call_index += 1

    conn.commit()

    # Verify
    row = conn.execute("SELECT COUNT(*) FROM llm_calls").fetchone()
    total = row[0] if row else 0
    conn.close()

    return inserted, total


if __name__ == "__main__":
    inserted, total = seed_database()
    print(f"Inserted {inserted} synthetic calls into {DB_PATH}")
    print(f"Total rows in llm_calls: {total}")
    print(f"Clusters: {', '.join(CLUSTERS.keys())}")
    print(f"Ready for: agentshrink analyse")
