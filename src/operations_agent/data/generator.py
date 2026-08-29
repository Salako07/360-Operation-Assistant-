"""High-performance, deterministic generator for NovaDesk enterprise synthetic dataset."""

from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
import random
import sqlite3
from typing import Any

from operations_agent.data.database import get_db_connection, init_db
from operations_agent.data.scenarios import DEMO_SCENARIOS

SEED = 42

INDUSTRIES = (
    "Financial Services",
    "Healthcare",
    "Education",
    "Retail",
    "Manufacturing",
    "Technology",
    "Logistics",
    "Professional Services",
    "Telecommunications",
    "Media",
)

COMPANY_SIZES = (
    "1-10",
    "11-50",
    "51-250",
    "251-1000",
    "1000+",
)

REGIONS = (
    ("North America", "United States"),
    ("North America", "Canada"),
    ("Europe", "United Kingdom"),
    ("Europe", "Germany"),
    ("Europe", "France"),
    ("Asia-Pacific", "Australia"),
    ("Asia-Pacific", "Singapore"),
    ("Asia-Pacific", "Japan"),
)

PLANS = {
    "Starter Monthly": {"mrr": Decimal("99.00"), "cycle": "monthly", "seats": 5, "segment": "small-business"},
    "Starter Annual": {"mrr": Decimal("79.00"), "cycle": "annual", "seats": 5, "segment": "small-business"},
    "Professional Monthly": {"mrr": Decimal("499.00"), "cycle": "monthly", "seats": 20, "segment": "mid-market"},
    "Professional Annual": {"mrr": Decimal("399.00"), "cycle": "annual", "seats": 20, "segment": "mid-market"},
    "Growth Annual": {"mrr": Decimal("1200.00"), "cycle": "annual", "seats": 50, "segment": "mid-market"},
    "Enterprise Monthly": {"mrr": Decimal("5200.00"), "cycle": "monthly", "seats": 100, "segment": "enterprise"},
    "Enterprise Annual": {"mrr": Decimal("4800.00"), "cycle": "annual", "seats": 100, "segment": "enterprise"},
}

FIRST_NAMES = (
    "Maya", "Daniel", "Aisha", "Leo", "Alex", "Elena", "Marcus", "Sophia",
    "David", "Chloe", "Liam", "Olivia", "Noah", "Emma", "James", "Ava",
    "William", "Isabella", "Benjamin", "Mia", "Lucas", "Harper", "Henry", "Evelyn",
)

LAST_NAMES = (
    "Chen", "Ortiz", "Rahman", "Martins", "Vance", "Kovacs", "Dupont", "Nakamura",
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis",
    "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson",
)

COMPANY_PREFIXES = (
    "Northstar", "Harbor", "Cedar", "Juniper", "Alpine", "Apex", "CloudScale", "Vanguard",
    "Summit", "Starlight", "OmniCorp", "BlueSky", "Horizon", "Pinnacle", "Nexus", "FinTech",
    "Atlas", "Matrix", "Solaria", "Quantum", "Delta", "Beacon", "Zenith", "Optima",
    "Titan", "Veritas", "Breeze", "AeroSpace", "Nova", "Vortex", "CyberShield", "Pulse",
)

COMPANY_SUFFIXES = (
    "Analytics", "Retail Group", "Health Partners", "Studio", "Logistics", "Digital", "Media",
    "Financial", "Education", "Solutions", "Dynamics", "Systems", "Global", "AI",
    "Tech", "Pharma", "Consulting", "Manufacturing", "Telecom", "Travel", "Labs",
)

KB_ARTICLES = (
    # Retention Policies
    ("KB-101", "Customer Retention Policy Overview", "Retention",
     "Standard retention workflows, early risk detection signals, and remediation guidelines for B2B SaaS accounts.",
     "retention,policy,overview,churn_risk,playbook", "2026-01-10",
     "NovaDesk Customer Retention Policy establishes proactive engagement protocols for at-risk accounts. Accounts showing a >20% decline in 30-day active sessions, failed renewal transactions, or open priority 1 support tickets must enter retention monitoring within 24 hours. A human operator must review and approve any consequential outreach or commercial incentives."),

    ("KB-102", "Churn-Risk Escalation Procedure", "Retention",
     "Step-by-step procedure for escalating high-churn-risk accounts to Customer Success Managers.",
     "churn,escalation,procedure,retention,csm", "2026-02-15",
     "When an account is flagged for churn risk due to payment failure, severe usage drop, or sponsor turnover, the CSM must schedule an account review within 48 hours. If the customer has submitted a formal cancellation request, initiate the executive offboarding and data retention interview."),

    ("KB-103", "High-Value Enterprise Customer Retention Playbook", "Retention",
     "Specialized retention procedures for Enterprise tier accounts with MRR exceeding $3,000.",
     "enterprise,high_value,retention,executive_sponsor,mrr", "2026-03-01",
     "Enterprise accounts with MRR > $3,000 receive dedicated VP-level sponsorship. Any unaddressed ticket older than 7 days triggers an automatic alert to the VP of Customer Experience. Renewal reviews must commence 90 days prior to contract expiration."),

    ("KB-105", "Commercial Discount and Concession Approval Policy", "Retention",
     "Authorization matrix and approval limits for renewal discounts and commercial concessions.",
     "discount,approval,pricing,commercial,concession", "2026-01-20",
     "Standard renewal discounts up to 10% can be authorized by Senior CSMs. Discounts between 11% and 25% require Director of Sales approval. Multi-year commitments (2-3 years) qualify for up to 30% discount with VP Finance sign-off."),

    ("KB-112", "Support Ticket Priority and Escalation Matrix", "Support",
     "SLA definitions, severity thresholds, and engineering escalation paths for customer support.",
     "support,sla,escalation,severity,urgent", "2026-02-01",
     "Support tickets are categorized into P1 (Urgent, 1-hour SLA response, 4-hour resolution target), P2 (High, 4-hour SLA response, 24-hour resolution target), P3 (Medium, 8-hour SLA response, 72-hour target), and P4 (Low, 24-hour SLA response). Repeated SLA breaches require Tier 3 Engineering assignment."),

    ("KB-143", "Retention Review Checklist for Mid-Market Accounts", "Retention",
     "Standard checklist for mid-market account managers conducting quarterly health audits.",
     "checklist,mid_market,health_audit,retention,churn", "2026-02-10",
     "Mid-market accounts on Growth Annual or Professional plans require periodic health audits verifying: 1) Active seat utilization > 70%, 2) On-time payment record over last 12 months, 3) Open ticket resolution status, 4) Upcoming contract renewal date within 60 days."),

    ("KB-187", "Incident Post-Mortem and Recovery Playbook: Reporting Outage", "Support",
     "Post-mortem analysis, customer communication templates, and service credit guidelines for the June 2026 reporting engine incident.",
     "incident,outage,reporting,reliability,playbook,service_credit,support", "2026-06-15",
     "On June 1-3, 2026, NovaDesk experienced a partial service disruption in scheduled executive reports. Impacted customers who experienced delivery delays are eligible for a 10% to 20% one-time service credit upon request. Customer communications must acknowledge the root-cause fix and reassure data export integrity."),

    ("KB-201", "Playbook: Payment Failure Recovery for Renewal Accounts", "Billing",
     "Standard operational procedure for managing renewal payment failures and dunning grace periods.",
     "billing,failed_payment,renewal,past_due,dunning", "2026-01-05",
     "When an annual or monthly renewal payment fails, NovaDesk initiates a 14-day dunning grace period. The automated billing gateway attempts retries on days 1, 3, 7, and 12. If unresolved by day 10, the operations agent initiates human-reviewed retention outreach to coordinate payment method updates before service suspension."),

    ("KB-240", "Customer Service Credit and Refund Authorization Guidelines", "Billing",
     "Rules governing refund authorization limits, service credit calculations, and invoice adjustments.",
     "refund,credit,authorization,billing_dispute,invoice", "2026-03-12",
     "Refunds up to $500 can be approved by Tier 2 Support Leads. Service credits up to 1 month MRR can be granted for verified SLA breaches or platform disruptions exceeding 4 hours. Disputed overage invoices resulting from technical calculation errors must be credited within 5 business days."),

    ("KB-305", "Workflow Automation Engine Architecture and Limits", "Product",
     "Technical specifications, execution quotas, and concurrency limits for NovaDesk workflow automation.",
     "workflow,automation,quotas,limits,architecture", "2026-01-15",
     "NovaDesk workflow engine supports up to 10,000 monthly executions on Professional, 50,000 on Growth, and custom quotas on Enterprise. Concurrency throttling activates when an account exceeds 100 simultaneous webhook triggers."),

    ("KB-310", "Enterprise SAML SSO and Identity Provider Integration Guide", "Product",
     "Configuration steps for Okta, Azure AD, and Google Workspace SAML 2.0 single sign-on.",
     "sso,saml,okta,azure_ad,security,integration", "2026-02-28",
     "Enterprise SAML SSO requires SHA-256 certificate signing and configured Assertion Consumer Service (ACS) URL. Solution Architects assist enterprise customers during setup and testing."),

    ("KB-315", "Webhook Troubleshooting and Endpoint Health Monitoring", "Product",
     "Diagnostic steps for resolving HTTP 500 errors, delivery retries, and webhook payload verification.",
     "webhook,troubleshooting,http_500,api,integration", "2026-03-20",
     "NovaDesk retries failed webhook deliveries with exponential backoff up to 5 attempts. If customer endpoints consistently return HTTP 500 or timeout (>10s), delivery is paused and an alert is dispatched to the customer technical administrator."),

    ("KB-405", "Customer Data Processing Addendum (DPA) and Compliance Guidelines", "Operations",
     "Legal frameworks, GDPR/CCPA compliance, and standard DPA execution guidelines.",
     "dpa,gdpr,compliance,legal,soc2,security", "2026-01-30",
     "Enterprise customers subject to GDPR or HIPAA may execute the standard NovaDesk Data Processing Addendum. Custom legal amendments require review by General Counsel within 5 business days."),

    ("KB-501", "Human-in-the-Loop Operational Approval Requirements", "Operations",
     "Policy outlining which autonomous operations actions require mandatory human supervisor approval.",
     "approval,human_in_the_loop,policy,operations,governance", "2026-01-01",
     "Any consequential action—including sending commercial retention outreach, issuing billing refunds > $100, granting discount concessions, or modifying active subscription contracts—requires explicit human operator approval before external dispatch."),
)


def generate_synthetic_enterprise_data(
    db_path: Path | str | None = None,
    customer_count: int = 10000,
    seed: int = SEED,
) -> dict[str, int]:
    """Generate deterministic, relational synthetic enterprise dataset for NovaDesk."""
    rng = random.Random(seed)
    init_db(db_path)
    conn = get_db_connection(db_path)

    # Clear existing tables for fresh deterministic seeding
    with conn:
        conn.execute("DELETE FROM customer_interactions;")
        conn.execute("DELETE FROM support_tickets;")
        conn.execute("DELETE FROM product_usage;")
        conn.execute("DELETE FROM invoices;")
        conn.execute("DELETE FROM transactions;")
        conn.execute("DELETE FROM subscriptions;")
        conn.execute("DELETE FROM customers;")
        conn.execute("DELETE FROM knowledge_base;")
        conn.execute("DELETE FROM account_managers;")

    # 1. Account Managers (50 total)
    account_managers_data = []
    am_ids = []
    for i in range(1, 51):
        emp_id = f"EMP-{i:03d}"
        am_ids.append(emp_id)
        fn = rng.choice(FIRST_NAMES)
        ln = rng.choice(LAST_NAMES)
        region, _ = rng.choice(REGIONS)
        team = f"{region} Customer Success"
        account_managers_data.append((
            emp_id, f"{fn} {ln}", f"{fn.lower()}.{ln.lower()}@novadesk.internal",
            team, region, 0
        ))

    # 2. Knowledge Base Articles (14 rich core articles + expanded documents = 35 articles)
    kb_data = []
    for art in KB_ARTICLES:
        kb_data.append((art[0], art[1], art[2], art[3], art[4], art[5], art[6]))

    # Additional supporting articles to reach 35 comprehensive documents
    categories = ["Retention", "Support", "Billing", "Operations", "Product"]
    for i in range(15, 36):
        cat = categories[i % len(categories)]
        art_id = f"KB-{i:03d}"
        title = f"Operational Standard: {cat} Workflow Guide Part {i - 14}"
        summary = f"Detailed procedures and guidelines for {cat.lower()} operational workflows in NovaDesk."
        tags = f"{cat.lower()},operations,standard,guide,playbook"
        content = f"Standard operating guidelines for NovaDesk {cat.lower()} workflows. Ensure customer alignment and audit trails."
        kb_data.append((art_id, title, cat, summary, tags, "2026-01-15", content))

    # 3. Deliberate Scenario Customers
    scenario_cust_ids = {s.customer_id: s for s in DEMO_SCENARIOS}

    customers_data = []
    subscriptions_data = []
    transactions_data = []
    invoices_data = []
    usage_data = []
    tickets_data = []
    interactions_data = []

    base_date = date(2026, 8, 29)

    scenario_cids = sorted(s.customer_id for s in DEMO_SCENARIOS)
    remaining_count = max(0, customer_count - len(scenario_cids))
    standard_cids = list(range(1000, 1000 + remaining_count))
    all_cids = scenario_cids + standard_cids

    # Helper for generating customers
    for cid in all_cids:
        scenario = scenario_cust_ids.get(cid)

        if scenario:
            # Deterministic scenario setup
            c_name = scenario.company_name
            fn = rng.choice(FIRST_NAMES)
            ln = rng.choice(LAST_NAMES)
            email = f"{fn.lower()}.{ln.lower()}@{c_name.lower().replace(' ', '-')}.example"
            industry = rng.choice(INDUSTRIES)
            comp_size = rng.choice(COMPANY_SIZES)
            reg, country = rng.choice(REGIONS)
            am = rng.choice(am_ids)

            if cid == 104:
                # Maya Chen, Northstar Analytics (flagship at-risk demo)
                fn, ln = "Maya", "Chen"
                c_name = "Northstar Analytics"
                email = "maya.chen@northstar-analytics.example"
                plan_key = "Growth Annual"
                status = "past_due"
                risk_segment = "At Risk"
                joined_on = "2024-01-15"
                contract_start = "2024-01-15"
                contract_end = "2026-08-31"
                sat_score = 4.2
                industry = "Technology"
                comp_size = "51-250"
                last_login_at = "2026-08-12T09:18:00"
            elif cid == 105:
                fn, ln = "Daniel", "Ortiz"
                c_name = "Harbor Retail Group"
                email = "daniel.ortiz@harbor-retail.example"
                plan_key = "Growth Annual"
                status = "active"
                risk_segment = "Healthy"
                joined_on = "2023-06-02"
                contract_start = "2023-06-02"
                contract_end = "2027-06-02"
                sat_score = 9.4
                industry = "Retail"
                comp_size = "51-250"
                last_login_at = "2026-08-26T15:40:00"
            elif cid == 106:
                fn, ln = "Aisha", "Rahman"
                c_name = "Cedar Health Partners"
                email = "aisha.rahman@cedar-health.example"
                plan_key = "Enterprise Annual"
                status = "active"
                risk_segment = "At Risk"
                joined_on = "2022-11-20"
                contract_start = "2022-11-20"
                contract_end = "2026-10-15"
                sat_score = 6.8
                industry = "Healthcare"
                comp_size = "251-1000"
                last_login_at = "2026-08-25T11:07:00"
            elif cid == 107:
                fn, ln = "Leo", "Martins"
                c_name = "Juniper Studio"
                email = "leo.martins@juniper-studio.example"
                plan_key = "Starter Monthly"
                status = "active"
                risk_segment = "Healthy"
                joined_on = "2026-08-22"
                contract_start = "2026-08-22"
                contract_end = "2026-09-22"
                sat_score = 8.5
                industry = "Media"
                comp_size = "1-10"
                last_login_at = None
            elif cid == 201:
                # Seasonal False Churn
                c_name = "Alpine Logistics"
                plan_key = "Professional Annual"
                status = "active"
                risk_segment = "Healthy"
                joined_on = "2023-04-10"
                contract_start = "2023-04-10"
                contract_end = "2027-04-10"
                sat_score = 8.8
                industry = "Logistics"
                comp_size = "51-250"
                last_login_at = "2026-08-28T14:20:00"
            elif cid == 207:
                # OmniCorp - Revenue Contraction / Failed Expansion
                c_name = "OmniCorp Solutions"
                plan_key = "Growth Annual"
                status = "past_due"
                risk_segment = "At Risk"
                joined_on = "2024-03-01"
                contract_start = "2024-03-01"
                contract_end = "2026-09-01"
                sat_score = 5.1
                industry = "Financial Services"
                comp_size = "251-1000"
                last_login_at = "2026-08-20T11:00:00"
            elif cid == 318:
                # Vortex Media - Genuine Usage Decline (Test C)
                c_name = "Vortex Media"
                plan_key = "Professional Annual"
                status = "active"
                risk_segment = "At Risk"
                joined_on = "2024-05-15"
                contract_start = "2024-05-15"
                contract_end = "2026-09-30"
                sat_score = 4.8
                industry = "Media"
                comp_size = "51-250"
                last_login_at = "2026-08-15T09:30:00"
            elif cid == 421:
                # CyberShield Tech - Unresolved Support Escalation (Test D)
                c_name = "CyberShield Tech"
                plan_key = "Enterprise Annual"
                status = "active"
                risk_segment = "At Risk"
                joined_on = "2023-08-01"
                contract_start = "2023-08-01"
                contract_end = "2026-11-01"
                sat_score = 5.5
                industry = "Technology"
                comp_size = "251-1000"
                last_login_at = "2026-08-27T16:45:00"
            elif cid == 512:
                # Apex Logistics - Healthy Operational Review (Test E)
                c_name = "Apex Logistics"
                plan_key = "Enterprise Annual"
                status = "active"
                risk_segment = "Healthy"
                joined_on = "2023-02-14"
                contract_start = "2023-02-14"
                contract_end = "2027-02-14"
                sat_score = 9.2
                industry = "Logistics"
                comp_size = "1000+"
                last_login_at = "2026-08-28T18:00:00"
            else:
                plan_key = rng.choice(list(PLANS.keys()))
                status = "active" if scenario.expected_risk != "high" else "past_due"
                risk_segment = "At Risk" if scenario.expected_risk in {"high", "critical"} else "Healthy"
                joined_on = "2024-02-01"
                contract_start = "2024-02-01"
                contract_end = "2026-12-31"
                sat_score = 5.0 if risk_segment == "At Risk" else 8.5
                last_login_at = "2026-08-20T10:00:00"

            plan_meta = PLANS[plan_key]
            mrr = float(plan_meta["mrr"])
            segment = plan_meta["segment"]

        else:
            # Standard Enterprise Distribution (9,967 customers)
            c_name = f"{rng.choice(COMPANY_PREFIXES)} {rng.choice(COMPANY_SUFFIXES)}"
            fn = rng.choice(FIRST_NAMES)
            ln = rng.choice(LAST_NAMES)
            email = f"{fn.lower()}.{ln.lower()}@{c_name.lower().replace(' ', '-')[:15]}.example"
            industry = rng.choice(INDUSTRIES)
            comp_size = rng.choice(COMPANY_SIZES)
            reg, country = rng.choice(REGIONS)
            am = rng.choice(am_ids)

            # Realistic plan distribution
            plan_roll = rng.random()
            if plan_roll < 0.40:
                plan_key = rng.choice(["Starter Monthly", "Starter Annual"])
            elif plan_roll < 0.75:
                plan_key = rng.choice(["Professional Monthly", "Professional Annual"])
            elif plan_roll < 0.90:
                plan_key = "Growth Annual"
            else:
                plan_key = rng.choice(["Enterprise Monthly", "Enterprise Annual"])

            plan_meta = PLANS[plan_key]
            mrr = float(plan_meta["mrr"])
            segment = plan_meta["segment"]

            # Signup dates distributed across last 3 years
            days_ago = rng.randint(10, 1000)
            signup_d = base_date - timedelta(days=days_ago)
            joined_on = signup_d.isoformat()
            contract_start = joined_on
            contract_end = (signup_d + timedelta(days=365)).isoformat()

            # Status and risk distribution
            risk_roll = rng.random()
            if risk_roll < 0.75:
                risk_segment = "Healthy"
                status = "active"
                sat_score = round(rng.uniform(7.5, 9.8), 1)
            elif risk_roll < 0.88:
                risk_segment = "Growing"
                status = "active"
                sat_score = round(rng.uniform(8.0, 10.0), 1)
            elif risk_roll < 0.96:
                risk_segment = "At Risk"
                status = "past_due" if rng.random() < 0.5 else "active"
                sat_score = round(rng.uniform(3.5, 6.0), 1)
            else:
                risk_segment = "Dormant"
                status = "cancelled" if rng.random() < 0.3 else "active"
                sat_score = round(rng.uniform(4.0, 7.0), 1)

            last_login_days = rng.randint(0, 45) if risk_segment != "Dormant" else rng.randint(45, 120)
            last_login_at = (base_date - timedelta(days=last_login_days, hours=rng.randint(1, 23))).isoformat() + "T10:00:00"

        customers_data.append((
            cid, f"{fn} {ln}", c_name, email, segment, plan_key,
            mrr, status, joined_on, last_login_at,
            industry, comp_size, country, reg, am,
            contract_start, contract_end, sat_score, risk_segment
        ))

        # 4. Subscriptions (1-2 per customer)
        sub_id = f"SUB-{cid:05d}-1"
        subscriptions_data.append((
            sub_id, cid, plan_key, plan_meta["cycle"],
            contract_start, contract_end, mrr,
            status, plan_meta["seats"], 1 if status == "active" else 0
        ))

        # 5. Transactions (~15-30 per customer on average across portfolio)
        signup_dt = date.fromisoformat(joined_on)
        if cid == 104:
            tx_count = 3
            transactions_data.append((
                "txn_104_20260801", 104, sub_id, "2026-08-01", 1200.0, "USD",
                "failed", "Growth Annual renewal installment", "Card declined by issuing bank", "renewal", "credit_card"
            ))
            transactions_data.append((
                "txn_104_20260701", 104, sub_id, "2026-07-01", 1200.0, "USD",
                "succeeded", "Growth Annual renewal installment", None, "payment", "credit_card"
            ))
            transactions_data.append((
                "txn_104_20260603", 104, sub_id, "2026-06-03", 240.0, "USD",
                "refunded", "Partial service credit for reporting outage", "Outage credit authorized", "refund", "credit_card"
            ))
        else:
            tx_count = rng.randint(12, 36) if cid > 200 else 18
            for t in range(tx_count):
                tx_date = signup_dt + timedelta(days=t * 30)
                if tx_date > base_date:
                    break
                tx_id = f"txn_{cid}_{tx_date.strftime('%Y%m%d')}_{t+1}"
                amount = mrr

                if cid in {202, 207, 306} and t == tx_count - 1:
                    tx_status = "failed"
                    tx_type = "renewal"
                    desc = f"{plan_key} renewal installment"
                    reason = "Card expired / declined"
                else:
                    tx_status = "succeeded"
                    tx_type = "payment"
                    desc = f"{plan_key} subscription fee"
                    reason = None

                transactions_data.append((
                    tx_id, cid, sub_id, tx_date.isoformat(), amount, "USD",
                    tx_status, desc, reason, tx_type, "credit_card"
                ))

        # 6. Invoices (1 per transaction)
        for t in range(min(tx_count, 12)):
            inv_date = signup_dt + timedelta(days=t * 30)
            if inv_date > base_date:
                break
            inv_id = f"INV-{cid:05d}-{t+1:03d}"
            due_date = inv_date + timedelta(days=14)
            if cid in {104, 207} and t >= tx_count - 2:
                inv_status = "overdue"
                paid_d = None
                overdue_days = 25
            else:
                inv_status = "paid"
                paid_d = (inv_date + timedelta(days=2)).isoformat()
                overdue_days = 0

            invoices_data.append((
                inv_id, cid, sub_id, inv_date.isoformat(), due_date.isoformat(),
                paid_d, mrr, inv_status, overdue_days
            ))

        # 7. Product Usage (Time-series data: 30-90 daily records per customer)
        usage_days = 60 if cid <= 300 else 15
        base_users = plan_meta["seats"]
        for u in range(usage_days):
            u_date = base_date - timedelta(days=usage_days - u)
            if u_date < signup_dt:
                continue

            u_id = f"USE-{cid:05d}-{u_date.strftime('%Y%m%d')}"

            # Calculate usage trajectory
            if cid == 104:
                # Declining usage for Northstar Analytics
                mult = max(0.2, 1.0 - (u / usage_days) * 0.7)
            elif cid == 201:
                # Seasonal summer dip in July/August
                mult = 0.4 if u_date.month in {7, 8} else 1.1
            elif cid == 318:
                # Vortex Media genuine usage decline (-45%)
                mult = max(0.3, 1.0 - (u / usage_days) * 0.5)
            elif risk_segment == "Growing":
                mult = 1.0 + (u / usage_days) * 0.4
            elif risk_segment == "At Risk":
                mult = max(0.2, 1.0 - (u / usage_days) * 0.6)
            elif risk_segment == "Dormant":
                mult = 0.05
            else:
                mult = 1.0 + (rng.random() - 0.5) * 0.15

            act_users = max(1, int(base_users * mult))
            sessions = act_users * rng.randint(2, 6)
            api_calls = sessions * rng.randint(10, 50)
            workflows = max(1, int(act_users * 3 * mult))
            automation_runs = workflows * rng.randint(5, 20)
            features = min(12, int(4 * mult) + rng.randint(1, 3))
            storage = round(float(act_users * 1.5), 2)

            usage_data.append((
                u_id, cid, u_date.isoformat(), act_users, sessions,
                api_calls, workflows, automation_runs, features, storage
            ))

        # 8. Support Tickets (~5 tickets per customer on average)
        ticket_count = rng.randint(1, 4) if risk_segment == "Healthy" else rng.randint(3, 8)
        if cid == 104:
            # Maya Chen explicit tickets matching tests
            tickets_data.append((
                "SUP-4821", cid, "2026-08-10T14:22:00", "2026-08-25T10:45:00", None,
                "open", "high", "Scheduled reports are delayed by several hours",
                "Customer reports recurring delivery delays in executive reports and says the issue is affecting monthly board review.",
                "reporting reliability", "breached", "Tier 2 Support", None, None
            ))
            tickets_data.append((
                "SUP-4756", cid, "2026-07-29T08:15:00", "2026-08-03T16:30:00", "2026-08-03T16:30:00",
                "resolved", "high", "Unable to export usage data",
                "CSV exports timed out for large workspaces. A workaround was provided.",
                "data export", "met", "Tier 1 Support", 120.0, 5
            ))
            tickets_data.append((
                "SUP-4688", cid, "2026-06-01T11:05:00", "2026-06-04T09:20:00", "2026-06-04T09:20:00",
                "resolved", "medium", "Request for service credit after reporting outage",
                "Customer requested compensation following a reporting outage.",
                "billing and service recovery", "met", "Tier 1 Support", 48.0, 4
            ))
        elif cid == 421:
            # CyberShield Tech unresolved critical ticket (Test D)
            tickets_data.append((
                "SUP-SEC-421", cid, "2026-08-15T09:00:00", "2026-08-28T16:00:00", None,
                "open", "urgent", "Critical security audit log export failure",
                "Enterprise security log export fails with 500 error, blocking compliance audit.",
                "Security", "breached", "Tier 3 Engineering", None, None
            ))
        else:
            for k in range(ticket_count):
                t_id = f"SUP-{cid:05d}-{k+1}"
                t_date = base_date - timedelta(days=rng.randint(5, 180))
                cat = rng.choice(["Billing", "Technical", "Integration", "Performance", "Security", "Account", "Bug", "Onboarding"])
                prio = rng.choice(["low", "medium", "high", "urgent"]) if risk_segment == "At Risk" else rng.choice(["low", "medium"])
                stat = "open" if rng.random() < 0.25 and risk_segment == "At Risk" else "resolved"
                res_d = None if stat == "open" else (t_date + timedelta(hours=rng.randint(4, 72))).isoformat() + "T12:00:00"
                sla = "breached" if stat == "open" and prio in {"high", "urgent"} else "met"
                subj = f"{cat} issue on {plan_key} account"
                summary = f"Logged ticket regarding {cat.lower()} functionality."

                tickets_data.append((
                    t_id, cid, t_date.isoformat() + "T10:00:00",
                    (t_date + timedelta(days=1)).isoformat() + "T10:00:00",
                    res_d, stat, prio, subj, summary, cat, sla, "Tier 1 Support",
                    24.0 if res_d else None, rng.randint(1, 5) if res_d else None
                ))

        # 9. Customer Interactions (~10 per customer)
        interaction_count = rng.randint(3, 12)
        for m in range(interaction_count):
            i_id = f"INT-{cid:05d}-{m+1}"
            i_date = base_date - timedelta(days=rng.randint(2, 200))
            i_type = rng.choice(["call", "email", "meeting", "chat", "note"])
            if cid == 104 and m == 0:
                sentiment = "negative"
                topic = "Reporting Delays & Renewal"
                summary = "Customer expressed deep frustration over report delays and questioned renewing."
            elif risk_segment == "At Risk":
                sentiment = rng.choice(["negative", "neutral"])
                topic = "Billing Friction & Support Follow-up"
                summary = "Customer noted frustration with recent service issues."
            elif risk_segment == "Growing":
                sentiment = "positive"
                topic = "Expansion & Seat Addition"
                summary = "Customer praised workflow automation efficiency and requested quote for 20 more seats."
            else:
                sentiment = rng.choice(["positive", "neutral"])
                topic = "Quarterly Check-in"
                summary = "Routine quarterly business review completed successfully."

            interactions_data.append((
                i_id, cid, am, i_date.isoformat() + "T14:30:00",
                i_type, sentiment, topic, summary
            ))

    # Fast Bulk Inserts within a single SQLite transaction
    with conn:
        conn.executemany(
            "INSERT OR REPLACE INTO account_managers VALUES (?, ?, ?, ?, ?, ?)",
            account_managers_data
        )
        conn.executemany(
            "INSERT OR REPLACE INTO knowledge_base VALUES (?, ?, ?, ?, ?, ?, ?)",
            kb_data
        )
        conn.executemany(
            "INSERT OR REPLACE INTO customers VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            customers_data
        )
        conn.executemany(
            "INSERT OR REPLACE INTO subscriptions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            subscriptions_data
        )
        conn.executemany(
            "INSERT OR REPLACE INTO transactions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            transactions_data
        )
        conn.executemany(
            "INSERT OR REPLACE INTO invoices VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            invoices_data
        )
        conn.executemany(
            "INSERT OR REPLACE INTO product_usage VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            usage_data
        )
        conn.executemany(
            "INSERT OR REPLACE INTO support_tickets VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            tickets_data
        )
        conn.executemany(
            "INSERT OR REPLACE INTO customer_interactions VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            interactions_data
        )

    conn.close()

    return {
        "customers": len(customers_data),
        "subscriptions": len(subscriptions_data),
        "transactions": len(transactions_data),
        "invoices": len(invoices_data),
        "usage_records": len(usage_data),
        "support_tickets": len(tickets_data),
        "interactions": len(interactions_data),
        "account_managers": len(account_managers_data),
        "knowledge_articles": len(kb_data),
        "investigation_scenarios": len(DEMO_SCENARIOS),
    }
