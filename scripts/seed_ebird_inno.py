from __future__ import annotations

import argparse
import shutil
import sqlite3
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BLANK_DB = ROOT / "data" / "OfficeAutomationBlank" / "office_automation.db"
TARGET_DB = ROOT / "data" / "ebirdInno.db"
SEED_DATE = "2026-07-04 10:00:00"


@dataclass(frozen=True)
class UserSeed:
    username: str
    full_name: str
    email: str
    mobile: str
    department: str
    role_id: int
    role_name: str
    is_admin: int
    shift_id: int
    leave_balance: float
    designation: str
    join_date: str
    manager_username: str | None
    official_email: str
    personal_email: str
    emergency_parent: str
    emergency_spouse: str | None
    skill_tags: tuple[str, ...]


USERS: tuple[UserSeed, ...] = (
    UserSeed(
        username="bijumon",
        full_name="Bijumon",
        email="bijumon@ebirdinnovation.local",
        mobile="+91-9847001101",
        department="Leadership",
        role_id=1,
        role_name="Admin",
        is_admin=1,
        shift_id=1,
        leave_balance=24.0,
        designation="CTO",
        join_date="2024-06-01",
        manager_username=None,
        official_email="cto@ebirdinnovation.local",
        personal_email="bijumon.personal@example.com",
        emergency_parent="R. Thankam - +91-9847002101",
        emergency_spouse="Anju - +91-9847003101",
        skill_tags=("platform architecture", "delivery leadership", "product strategy"),
    ),
    UserSeed(
        username="arshadev",
        full_name="Arshadev",
        email="arshadev@ebirdinnovation.local",
        mobile="+91-9847001102",
        department="Research and Development",
        role_id=3,
        role_name="Manager",
        is_admin=0,
        shift_id=1,
        leave_balance=21.0,
        designation="R&D Head",
        join_date="2024-09-15",
        manager_username="bijumon",
        official_email="rnd.head@ebirdinnovation.local",
        personal_email="arshadev.personal@example.com",
        emergency_parent="S. Devi - +91-9847002102",
        emergency_spouse=None,
        skill_tags=("embedded systems", "hardware prototyping", "vendor coordination"),
    ),
    UserSeed(
        username="nissar",
        full_name="Nissar",
        email="nissar@ebirdinnovation.local",
        mobile="+91-9847001103",
        department="Sales and Marketing",
        role_id=3,
        role_name="Manager",
        is_admin=0,
        shift_id=1,
        leave_balance=20.0,
        designation="Sales and Marketing Head",
        join_date="2024-10-01",
        manager_username="bijumon",
        official_email="sales.head@ebirdinnovation.local",
        personal_email="nissar.personal@example.com",
        emergency_parent="A. Rahmath - +91-9847002103",
        emergency_spouse="Shabna - +91-9847003103",
        skill_tags=("channel sales", "client proposals", "market development"),
    ),
    UserSeed(
        username="roshna",
        full_name="Roshna",
        email="roshna@ebirdinnovation.local",
        mobile="+91-9847001104",
        department="Software Engineering",
        role_id=3,
        role_name="Manager",
        is_admin=0,
        shift_id=1,
        leave_balance=19.0,
        designation="Software Lead",
        join_date="2025-01-06",
        manager_username="bijumon",
        official_email="software.lead@ebirdinnovation.local",
        personal_email="roshna.personal@example.com",
        emergency_parent="P. Latha - +91-9847002104",
        emergency_spouse=None,
        skill_tags=("backend engineering", "sprint planning", "erp modules"),
    ),
    UserSeed(
        username="sumesh",
        full_name="Sumesh",
        email="sumesh@ebirdinnovation.local",
        mobile="+91-9847001105",
        department="Customer Support",
        role_id=3,
        role_name="Manager",
        is_admin=0,
        shift_id=2,
        leave_balance=18.0,
        designation="Lead Customer Support",
        join_date="2025-02-10",
        manager_username="bijumon",
        official_email="support.lead@ebirdinnovation.local",
        personal_email="sumesh.personal@example.com",
        emergency_parent="M. Rajan - +91-9847002105",
        emergency_spouse="Deepa - +91-9847003105",
        skill_tags=("customer onboarding", "issue triage", "support operations"),
    ),
    UserSeed(
        username="jalan",
        full_name="Jalan",
        email="jalan@ebirdinnovation.local",
        mobile="+91-9847001106",
        department="Production",
        role_id=3,
        role_name="Manager",
        is_admin=0,
        shift_id=1,
        leave_balance=18.0,
        designation="Production Manager",
        join_date="2025-03-01",
        manager_username="bijumon",
        official_email="production.manager@ebirdinnovation.local",
        personal_email="jalan.personal@example.com",
        emergency_parent="P. Soman - +91-9847002106",
        emergency_spouse=None,
        skill_tags=("production planning", "quality control", "assembly workflow"),
    ),
    UserSeed(
        username="sreedhanya",
        full_name="SreeDhanya",
        email="sreedhanya@ebirdinnovation.local",
        mobile="+91-9847001107",
        department="Software Engineering",
        role_id=6,
        role_name="Software Engineer",
        is_admin=0,
        shift_id=1,
        leave_balance=16.0,
        designation="Software Engineer",
        join_date="2025-07-14",
        manager_username="roshna",
        official_email="sreedhanya@ebirdinnovation.local",
        personal_email="sreedhanya.personal@example.com",
        emergency_parent="K. Sindhu - +91-9847002107",
        emergency_spouse=None,
        skill_tags=("python", "database integrations", "ui support"),
    ),
    UserSeed(
        username="visakh",
        full_name="Visakh",
        email="visakh@ebirdinnovation.local",
        mobile="+91-9847001108",
        department="Software Engineering",
        role_id=4,
        role_name="Employee",
        is_admin=0,
        shift_id=2,
        leave_balance=15.0,
        designation="Android Developer",
        join_date="2025-08-18",
        manager_username="roshna",
        official_email="visakh@ebirdinnovation.local",
        personal_email="visakh.personal@example.com",
        emergency_parent="P. Suresh - +91-9847002108",
        emergency_spouse=None,
        skill_tags=("android", "iot integration", "mobile qa"),
    ),
    UserSeed(
        username="dipin",
        full_name="Dipin",
        email="dipin@ebirdinnovation.local",
        mobile="+91-9847001109",
        department="Administration",
        role_id=4,
        role_name="Employee",
        is_admin=0,
        shift_id=1,
        leave_balance=17.0,
        designation="Office Admin",
        join_date="2025-04-07",
        manager_username="bijumon",
        official_email="office.admin@ebirdinnovation.local",
        personal_email="dipin.personal@example.com",
        emergency_parent="K. Thankachan - +91-9847002109",
        emergency_spouse=None,
        skill_tags=("office coordination", "purchase follow-up", "document control"),
    ),
)

DEPARTMENTS = (
    "Leadership",
    "Research and Development",
    "Sales and Marketing",
    "Software Engineering",
    "Customer Support",
    "Production",
    "Administration",
)

EXPENSE_CATEGORIES = (
    ("Hardware and Electronics", "Controllers, boards, sensors, locks, and test hardware"),
    ("Software and SaaS", "Cloud subscriptions, licenses, productivity tools"),
    ("Travel and Client Meetings", "Travel, food, local conveyance, customer visits"),
    ("Office and Admin", "Stationery, utilities, office maintenance, admin purchases"),
    ("Marketing and Events", "Brochures, banners, demo kits, campaigns"),
    ("Production and Prototyping", "Fabrication, assembly consumables, prototype material"),
    ("Support and Service", "Service visits, replacement parts, support consumables"),
)

PROJECTS = (
    {
        "name": "eOffice - ERP",
        "budget_limit": 1800000.0,
        "current_spending": 412500.0,
        "status": "active",
        "description": "Internal and client-ready ERP platform covering HR, attendance, office workflows, approvals, and reporting.",
        "startDate": "2026-01-08 09:30:00",
        "endDate": "2026-12-20 18:00:00",
    },
    {
        "name": "eGate Development",
        "budget_limit": 1350000.0,
        "current_spending": 568000.0,
        "status": "active",
        "description": "Controller, firmware, dashboard, and installation process upgrades for the eGate automatic gate opening system.",
        "startDate": "2026-01-15 09:30:00",
        "endDate": "2026-10-30 18:00:00",
    },
    {
        "name": "Android Smart Home",
        "budget_limit": 920000.0,
        "current_spending": 247000.0,
        "status": "active",
        "description": "Android application for smart-home control with device onboarding, scene automation, and alert handling for eGard.",
        "startDate": "2026-02-03 09:30:00",
        "endDate": "2026-11-28 18:00:00",
    },
)

PROJECT_MEMBERS = {
    "eOffice - ERP": (
        ("bijumon", "executive_sponsor"),
        ("roshna", "project_lead"),
        ("sreedhanya", "backend_engineer"),
        ("dipin", "business_operations"),
    ),
    "eGate Development": (
        ("arshadev", "project_owner"),
        ("jalan", "production_manager"),
        ("bijumon", "technical_sponsor"),
        ("sumesh", "service_readiness"),
    ),
    "Android Smart Home": (
        ("roshna", "delivery_lead"),
        ("visakh", "android_lead"),
        ("sreedhanya", "integration_support"),
        ("arshadev", "iot_advisor"),
    ),
}

PRODUCT_FACTS = (
    (
        "eGate Automatic Gate Opening System",
        "An automated gate opening solution for residential, commercial, and institutional entrances with controller and installation support.",
    ),
    (
        "eGard - Home Security and Automation",
        "A smart home security and automation offering focused on mobile control, alerts, and integrated device management.",
    ),
)

HOLIDAYS = (
    ("2026-01-01", "New Year Holiday", "Company", "Company-wide new year holiday", 0),
    ("2026-01-14", "Makaravilakku", "Festival", "Regional festival holiday", 0),
    ("2026-01-26", "Republic Day", "National", "National holiday", 0),
    ("2026-03-04", "Shivaratri", "Festival", "Festival holiday observed in Kerala", 1),
    ("2026-03-29", "Easter", "Festival", "Festival holiday", 0),
    ("2026-04-02", "Maundy Thursday", "Festival", "Pre-Easter observance", 1),
    ("2026-04-03", "Good Friday", "Festival", "Company holiday for Good Friday", 0),
    ("2026-04-14", "Vishu", "Festival", "Kerala new year festival holiday", 0),
    ("2026-05-01", "Labour Day", "National", "Workers day holiday", 0),
    ("2026-06-17", "Bakrid", "Festival", "Festival holiday", 0),
)

LEAVE_REQUESTS = (
    {
        "username": "bijumon",
        "leave_type": "casual",
        "start_date": "2026-02-12",
        "end_date": "2026-02-13",
        "requested_days": 2.0,
        "reason": "Family function travel",
        "request_channel": "ui",
        "request_message": "Applying for two days leave for family travel.",
        "status": "approved",
        "manager_decision_note": "Approved as planned leave.",
        "submitted_at": "2026-02-01 09:15:00",
        "approved_at": "2026-02-02 11:00:00",
        "rejected_at": None,
        "cancelled_at": None,
        "team_notified_at": "2026-02-02 11:30:00",
    },
    {
        "username": "arshadev",
        "leave_type": "sick",
        "start_date": "2026-01-22",
        "end_date": "2026-01-23",
        "requested_days": 2.0,
        "reason": "Viral fever and rest",
        "request_channel": "whatsapp",
        "request_message": "Not feeling well. Need sick leave for two days.",
        "status": "approved",
        "manager_decision_note": "Take rest and update on return.",
        "submitted_at": "2026-01-22 07:45:00",
        "approved_at": "2026-01-22 08:10:00",
        "rejected_at": None,
        "cancelled_at": None,
        "team_notified_at": "2026-01-22 08:25:00",
    },
    {
        "username": "nissar",
        "leave_type": "casual",
        "start_date": "2026-03-16",
        "end_date": "2026-03-16",
        "requested_days": 1.0,
        "reason": "Client-side personal documentation work",
        "request_channel": "ui",
        "request_message": "Need one casual leave day for personal documentation.",
        "status": "approved",
        "manager_decision_note": "Approved.",
        "submitted_at": "2026-03-10 18:20:00",
        "approved_at": "2026-03-11 09:00:00",
        "rejected_at": None,
        "cancelled_at": None,
        "team_notified_at": "2026-03-11 09:10:00",
    },
    {
        "username": "roshna",
        "leave_type": "casual",
        "start_date": "2026-04-27",
        "end_date": "2026-04-29",
        "requested_days": 3.0,
        "reason": "Planned family trip",
        "request_channel": "ui",
        "request_message": "Applying leave for three days after sprint handover.",
        "status": "approved",
        "manager_decision_note": "Approved after sprint handover plan shared.",
        "submitted_at": "2026-04-15 17:40:00",
        "approved_at": "2026-04-16 10:00:00",
        "rejected_at": None,
        "cancelled_at": None,
        "team_notified_at": "2026-04-16 10:20:00",
    },
    {
        "username": "sumesh",
        "leave_type": "casual",
        "start_date": "2026-05-18",
        "end_date": "2026-05-18",
        "requested_days": 1.0,
        "reason": "School admission work at home",
        "request_channel": "ui",
        "request_message": "Need one day casual leave for admission work.",
        "status": "approved",
        "manager_decision_note": "Approved.",
        "submitted_at": "2026-05-12 13:30:00",
        "approved_at": "2026-05-13 09:30:00",
        "rejected_at": None,
        "cancelled_at": None,
        "team_notified_at": "2026-05-13 09:45:00",
    },
    {
        "username": "jalan",
        "leave_type": "casual",
        "start_date": "2026-02-24",
        "end_date": "2026-02-24",
        "requested_days": 1.0,
        "reason": "Bank and property registration work",
        "request_channel": "ui",
        "request_message": "Requesting one day leave for bank-related work.",
        "status": "approved",
        "manager_decision_note": "Approved.",
        "submitted_at": "2026-02-20 16:00:00",
        "approved_at": "2026-02-21 09:15:00",
        "rejected_at": None,
        "cancelled_at": None,
        "team_notified_at": "2026-02-21 09:30:00",
    },
    {
        "username": "sreedhanya",
        "leave_type": "sick",
        "start_date": "2026-03-05",
        "end_date": "2026-03-05",
        "requested_days": 1.0,
        "reason": "Migraine and doctor consultation",
        "request_channel": "whatsapp",
        "request_message": "Severe migraine today. Requesting sick leave.",
        "status": "approved",
        "manager_decision_note": "Approved. Log updates tomorrow.",
        "submitted_at": "2026-03-05 08:05:00",
        "approved_at": "2026-03-05 08:20:00",
        "rejected_at": None,
        "cancelled_at": None,
        "team_notified_at": "2026-03-05 08:35:00",
    },
    {
        "username": "visakh",
        "leave_type": "casual",
        "start_date": "2026-06-11",
        "end_date": "2026-06-12",
        "requested_days": 2.0,
        "reason": "Brother's engagement function",
        "request_channel": "ui",
        "request_message": "Need two days leave for family event.",
        "status": "approved",
        "manager_decision_note": "Approved after mobile build submission.",
        "submitted_at": "2026-06-02 18:00:00",
        "approved_at": "2026-06-03 10:15:00",
        "rejected_at": None,
        "cancelled_at": None,
        "team_notified_at": "2026-06-03 10:30:00",
    },
    {
        "username": "dipin",
        "leave_type": "casual",
        "start_date": "2026-01-09",
        "end_date": "2026-01-09",
        "requested_days": 1.0,
        "reason": "Passport renewal appointment",
        "request_channel": "ui",
        "request_message": "Requesting one day leave for passport office appointment.",
        "status": "approved",
        "manager_decision_note": "Approved.",
        "submitted_at": "2026-01-06 15:40:00",
        "approved_at": "2026-01-07 09:05:00",
        "rejected_at": None,
        "cancelled_at": None,
        "team_notified_at": "2026-01-07 09:10:00",
    },
    {
        "username": "sreedhanya",
        "leave_type": "casual",
        "start_date": "2026-07-04",
        "end_date": "2026-07-04",
        "requested_days": 1.0,
        "reason": "Planned hometown visit",
        "request_channel": "ui",
        "request_message": "Applying for one day leave for hometown travel.",
        "status": "pending_manager_approval",
        "manager_decision_note": None,
        "submitted_at": "2026-07-03 17:10:00",
        "approved_at": None,
        "rejected_at": None,
        "cancelled_at": None,
        "team_notified_at": None,
    },
    {
        "username": "visakh",
        "leave_type": "casual",
        "start_date": "2026-04-20",
        "end_date": "2026-04-21",
        "requested_days": 2.0,
        "reason": "Leave request during release freeze",
        "request_channel": "ui",
        "request_message": "Need two days casual leave next week.",
        "status": "rejected",
        "manager_decision_note": "Release freeze for smart home beta. Reapply after milestone.",
        "submitted_at": "2026-04-17 14:20:00",
        "approved_at": None,
        "rejected_at": "2026-04-17 17:10:00",
        "cancelled_at": None,
        "team_notified_at": "2026-04-17 17:20:00",
    },
    {
        "username": "nissar",
        "leave_type": "casual",
        "start_date": "2026-06-25",
        "end_date": "2026-06-27",
        "requested_days": 3.0,
        "reason": "Outstation travel",
        "request_channel": "ui",
        "request_message": "Applied leave but travel plan postponed.",
        "status": "cancelled",
        "manager_decision_note": "Cancelled by requester after plan change.",
        "submitted_at": "2026-06-14 12:30:00",
        "approved_at": None,
        "rejected_at": None,
        "cancelled_at": "2026-06-18 11:00:00",
        "team_notified_at": "2026-06-18 11:10:00",
    },
)

EXPENSES = (
    ("2026-01-07", "Software and SaaS", "general", "Zoho Workplace annual renewal", "Zoho Corp", 18450.0, "bijumon", "dipin", "approved"),
    ("2026-01-18", "Hardware and Electronics", "eGate Development", "Prototype relay board and RF receiver modules", "TechAxis Components", 42600.0, "arshadev", "jalan", "approved"),
    ("2026-01-29", "Office and Admin", "general", "Printer toner, stationery, and filing supplies", "Metro Office Mart", 7850.0, "dipin", "dipin", "approved"),
    ("2026-02-06", "Travel and Client Meetings", "eOffice - ERP", "Client discovery visit and local conveyance", "FastTrack Cabs", 6350.0, "nissar", "nissar", "approved"),
    ("2026-02-12", "Production and Prototyping", "eGate Development", "Laser-cut brackets and enclosure samples", "FabWorks Kochi", 28900.0, "jalan", "jalan", "approved"),
    ("2026-02-24", "Software and SaaS", "Android Smart Home", "Firebase paid usage and test reporting tools", "Google Cloud", 11240.0, "roshna", "visakh", "approved"),
    ("2026-03-03", "Marketing and Events", "general", "Demo banner and product brochure print run", "Prime Prints", 15400.0, "nissar", "dipin", "approved"),
    ("2026-03-11", "Hardware and Electronics", "Android Smart Home", "Android test handset and IoT dev boards", "MobiWorld Distributors", 33800.0, "visakh", "visakh", "approved"),
    ("2026-03-21", "Office and Admin", "general", "UPS battery replacement and office maintenance", "PowerSafe Systems", 14200.0, "dipin", "dipin", "approved"),
    ("2026-03-28", "Support and Service", "eGate Development", "Field service consumables and connector kits", "GateServe Supplies", 9650.0, "sumesh", "sumesh", "approved"),
    ("2026-04-08", "Software and SaaS", "eOffice - ERP", "UI library and issue tracking license top-up", "Atlassian", 22180.0, "roshna", "sreedhanya", "approved"),
    ("2026-04-19", "Travel and Client Meetings", "eGate Development", "Site inspection trip for gate installation review", "Kerala Travels", 9180.0, "arshadev", "jalan", "approved"),
    ("2026-04-26", "Production and Prototyping", "eGate Development", "Motor mount revision samples", "Precision Fab", 18650.0, "jalan", "jalan", "approved"),
    ("2026-05-06", "Hardware and Electronics", "eGate Development", "Controller PCB batch and sensor set", "Innotech Circuits", 51200.0, "arshadev", "arshadev", "approved"),
    ("2026-05-13", "Software and SaaS", "general", "Antivirus and endpoint management renewal", "SecureNet", 12800.0, "bijumon", "dipin", "approved"),
    ("2026-05-24", "Travel and Client Meetings", "Android Smart Home", "Customer pilot visit and meal reimbursement", "TripMate", 5740.0, "visakh", "visakh", "approved"),
    ("2026-06-04", "Support and Service", "general", "AMC spares and installation support toolkit", "ServiceHub", 16750.0, "sumesh", "sumesh", "approved"),
    ("2026-06-14", "Marketing and Events", "general", "Product demo standees and launch collateral", "BrandEdge", 19800.0, "nissar", "dipin", "approved"),
    ("2026-06-22", "Office and Admin", "general", "Internet backup router and office pantry restock", "City Retail", 9340.0, "dipin", "dipin", "approved"),
    ("2026-07-02", "Software and SaaS", "eOffice - ERP", "Backup storage and monitoring invoices", "Azure India", 17320.0, "bijumon", "sreedhanya", "approved"),
)

PURCHASE_REQUESTS = (
    {
        "requester": "dipin",
        "title": "Office laser printer replacement",
        "description": "Replace the failing office printer with a duplex network laser printer.",
        "amount": 28500.0,
        "justification": "Current printer has recurring paper-feed issues affecting invoices and dispatch documents.",
        "project_scope": "general",
        "project_name": None,
        "status": "approved",
        "manager": "bijumon",
        "current_approver": None,
        "decision_note": "Approved for admin operations continuity.",
        "request_channel": "ui",
        "created_at": "2026-01-20 10:10:00",
        "approved_at": "2026-01-21 09:30:00",
        "rejected_at": None,
        "cancelled_at": None,
        "actions": (
            ("dipin", "submitted", "ui", "Submitted printer replacement request.", "bijumon", "2026-01-20 10:10:00"),
            ("bijumon", "approved", "ui", "Approved for immediate purchase.", None, "2026-01-21 09:30:00"),
        ),
    },
    {
        "requester": "visakh",
        "title": "Android test device purchase",
        "description": "Purchase two mid-range Android devices for smart-home app QA.",
        "amount": 36400.0,
        "justification": "Needed to validate onboarding and notification behavior across Android versions.",
        "project_scope": "project",
        "project_name": "Android Smart Home",
        "status": "approved",
        "manager": "roshna",
        "current_approver": None,
        "decision_note": "Approved after sprint planning review.",
        "request_channel": "ui",
        "created_at": "2026-02-09 16:00:00",
        "approved_at": "2026-02-10 09:45:00",
        "rejected_at": None,
        "cancelled_at": None,
        "actions": (
            ("visakh", "submitted", "ui", "Requested two Android QA devices.", "roshna", "2026-02-09 16:00:00"),
            ("roshna", "approved", "ui", "Approved within project budget.", None, "2026-02-10 09:45:00"),
        ),
    },
    {
        "requester": "arshadev",
        "title": "Controller board prototype batch",
        "description": "Order a small prototype batch of revised eGate controller boards.",
        "amount": 68400.0,
        "justification": "Required for field validation before production lock.",
        "project_scope": "project",
        "project_name": "eGate Development",
        "status": "approved",
        "manager": "bijumon",
        "current_approver": None,
        "decision_note": "Approved. Track against eGate prototype budget.",
        "request_channel": "whatsapp",
        "created_at": "2026-03-07 11:20:00",
        "approved_at": "2026-03-07 13:10:00",
        "rejected_at": None,
        "cancelled_at": None,
        "actions": (
            ("arshadev", "submitted", "whatsapp", "Need prototype controller board batch for field trials.", "bijumon", "2026-03-07 11:20:00"),
            ("bijumon", "approved", "whatsapp", "Approved for prototype validation.", None, "2026-03-07 13:10:00"),
        ),
    },
    {
        "requester": "nissar",
        "title": "Expo collateral and demo booth material",
        "description": "Procure printed collateral, standees, and giveaway kits for a local expo.",
        "amount": 22800.0,
        "justification": "Needed for product visibility and live lead capture.",
        "project_scope": "general",
        "project_name": None,
        "status": "cancelled",
        "manager": "bijumon",
        "current_approver": None,
        "decision_note": "Cancelled after event participation was postponed.",
        "request_channel": "ui",
        "created_at": "2026-04-05 12:15:00",
        "approved_at": None,
        "rejected_at": None,
        "cancelled_at": "2026-04-09 10:10:00",
        "actions": (
            ("nissar", "submitted", "ui", "Requested expo collateral budget.", "bijumon", "2026-04-05 12:15:00"),
            ("nissar", "cancelled", "ui", "Expo participation postponed.", None, "2026-04-09 10:10:00"),
        ),
    },
    {
        "requester": "sreedhanya",
        "title": "Additional ERP staging VM",
        "description": "Provision an extra staging VM for ERP module parallel testing.",
        "amount": 14800.0,
        "justification": "Current shared staging environment is a bottleneck for concurrent validation.",
        "project_scope": "project",
        "project_name": "eOffice - ERP",
        "status": "approved",
        "manager": "roshna",
        "current_approver": None,
        "decision_note": "Approved to speed up test cycles.",
        "request_channel": "ui",
        "created_at": "2026-05-16 15:30:00",
        "approved_at": "2026-05-17 09:20:00",
        "rejected_at": None,
        "cancelled_at": None,
        "actions": (
            ("sreedhanya", "submitted", "ui", "Requested dedicated staging VM.", "roshna", "2026-05-16 15:30:00"),
            ("roshna", "approved", "ui", "Approved under ERP infra budget.", None, "2026-05-17 09:20:00"),
        ),
    },
    {
        "requester": "sumesh",
        "title": "Service toolkit replenishment",
        "description": "Purchase replacement crimp tools, multimeter, and connector stock for service visits.",
        "amount": 19600.0,
        "justification": "Existing field toolkit is incomplete and slowing installations.",
        "project_scope": "general",
        "project_name": None,
        "status": "rejected",
        "manager": "bijumon",
        "current_approver": None,
        "decision_note": "Revise request with itemized vendor quotation.",
        "request_channel": "whatsapp",
        "created_at": "2026-06-06 09:40:00",
        "approved_at": None,
        "rejected_at": "2026-06-06 14:05:00",
        "cancelled_at": None,
        "actions": (
            ("sumesh", "submitted", "whatsapp", "Need to replenish field service toolkit.", "bijumon", "2026-06-06 09:40:00"),
            ("bijumon", "rejected", "whatsapp", "Share itemized quotation and urgency split.", None, "2026-06-06 14:05:00"),
        ),
    },
    {
        "requester": "jalan",
        "title": "Assembly workstation upgrade",
        "description": "Upgrade one assembly workstation with ESD mat, bench light, and tool rack.",
        "amount": 25400.0,
        "justification": "Required to improve consistency in gate controller assembly and inspection.",
        "project_scope": "project",
        "project_name": "eGate Development",
        "status": "pending_manager_approval",
        "manager": "bijumon",
        "current_approver": "bijumon",
        "decision_note": None,
        "request_channel": "ui",
        "created_at": "2026-07-03 18:05:00",
        "approved_at": None,
        "rejected_at": None,
        "cancelled_at": None,
        "actions": (
            ("jalan", "submitted", "ui", "Requested assembly workstation upgrade kit.", "bijumon", "2026-07-03 18:05:00"),
        ),
    },
)

TASKS = (
    {
        "title": "Finalize employee master and attendance rules",
        "description": "Define department-wise attendance, leave mapping, and employee onboarding rules for ERP rollout.",
        "status": "completed",
        "scheduled_date": "2026-01-10 09:30:00",
        "due_date": "2026-01-18 18:00:00",
        "priority": "high",
        "assignee": "sreedhanya",
        "created_by": "roshna",
        "completed_at": "2026-01-17 17:40:00",
        "status_info": "Employee master and attendance policy screens validated.",
        "todays_task": "2026-01-14",
        "project_name": "eOffice - ERP",
        "type": "task",
    },
    {
        "title": "Prepare gate controller prototype BOM",
        "description": "Consolidate BOM for revised controller board, enclosure, RF receiver, and mounting hardware.",
        "status": "completed",
        "scheduled_date": "2026-01-16 10:00:00",
        "due_date": "2026-01-25 18:00:00",
        "priority": "high",
        "assignee": "arshadev",
        "created_by": "bijumon",
        "completed_at": "2026-01-24 16:30:00",
        "status_info": "Prototype BOM frozen for first validation batch.",
        "todays_task": "2026-01-22",
        "project_name": "eGate Development",
        "type": "task",
    },
    {
        "title": "Create smart-home app onboarding wireframes",
        "description": "Draft device onboarding and room assignment flows for Android smart-home experience.",
        "status": "completed",
        "scheduled_date": "2026-02-04 09:30:00",
        "due_date": "2026-02-12 18:00:00",
        "priority": "medium",
        "assignee": "visakh",
        "created_by": "roshna",
        "completed_at": "2026-02-11 15:20:00",
        "status_info": "Initial onboarding flow approved for development.",
        "todays_task": "2026-02-08",
        "project_name": "Android Smart Home",
        "type": "task",
    },
    {
        "title": "Map purchase workflow for ERP approvals",
        "description": "Document approval states and actor roles for purchase request workflow in eOffice.",
        "status": "completed",
        "scheduled_date": "2026-02-18 09:45:00",
        "due_date": "2026-02-27 18:00:00",
        "priority": "high",
        "assignee": "roshna",
        "created_by": "bijumon",
        "completed_at": "2026-02-26 18:10:00",
        "status_info": "Approval flow signed off by leadership.",
        "todays_task": "2026-02-24",
        "project_name": "eOffice - ERP",
        "type": "task",
    },
    {
        "title": "Validate gate motor mount fitment",
        "description": "Test revised motor mount geometry against two gate assembly models.",
        "status": "completed",
        "scheduled_date": "2026-03-01 10:30:00",
        "due_date": "2026-03-09 18:00:00",
        "priority": "medium",
        "assignee": "jalan",
        "created_by": "arshadev",
        "completed_at": "2026-03-08 17:00:00",
        "status_info": "Revision 2 fitment accepted for fabrication.",
        "todays_task": "2026-03-05",
        "project_name": "eGate Development",
        "type": "task",
    },
    {
        "title": "Set up Android beta notification test matrix",
        "description": "Define test coverage for alert delivery, offline recovery, and room-wise notification preferences.",
        "status": "completed",
        "scheduled_date": "2026-03-15 09:30:00",
        "due_date": "2026-03-23 18:00:00",
        "priority": "medium",
        "assignee": "visakh",
        "created_by": "roshna",
        "completed_at": "2026-03-22 16:45:00",
        "status_info": "Notification QA matrix shared with team.",
        "todays_task": "2026-03-19",
        "project_name": "Android Smart Home",
        "type": "task",
    },
    {
        "title": "Create March support issue summary",
        "description": "Compile top customer issues, resolution timelines, and recurring field-service gaps.",
        "status": "completed",
        "scheduled_date": "2026-03-24 11:00:00",
        "due_date": "2026-03-30 18:00:00",
        "priority": "medium",
        "assignee": "sumesh",
        "created_by": "bijumon",
        "completed_at": "2026-03-29 17:10:00",
        "status_info": "Support summary shared for product and service review.",
        "todays_task": "2026-03-28",
        "project_name": "general",
        "type": "task",
    },
    {
        "title": "Implement leave approval timeline UI",
        "description": "Add timeline view for leave request submission, decision, and staff notification.",
        "status": "completed",
        "scheduled_date": "2026-04-05 09:30:00",
        "due_date": "2026-04-16 18:00:00",
        "priority": "high",
        "assignee": "sreedhanya",
        "created_by": "roshna",
        "completed_at": "2026-04-15 18:20:00",
        "status_info": "Timeline UI merged and smoke-tested.",
        "todays_task": "2026-04-11",
        "project_name": "eOffice - ERP",
        "type": "task",
    },
    {
        "title": "Prepare field installation checklist v2",
        "description": "Refine site survey, wiring, and safety checklist for eGate installations.",
        "status": "completed",
        "scheduled_date": "2026-04-10 10:00:00",
        "due_date": "2026-04-20 18:00:00",
        "priority": "high",
        "assignee": "sumesh",
        "created_by": "arshadev",
        "completed_at": "2026-04-18 16:40:00",
        "status_info": "Checklist adopted by field service team.",
        "todays_task": "2026-04-14",
        "project_name": "eGate Development",
        "type": "task",
    },
    {
        "title": "Review June marketing follow-up funnel",
        "description": "Analyze lead response time and proposal conversion from recent campaigns.",
        "status": "completed",
        "scheduled_date": "2026-05-03 11:15:00",
        "due_date": "2026-05-12 18:00:00",
        "priority": "medium",
        "assignee": "nissar",
        "created_by": "bijumon",
        "completed_at": "2026-05-11 17:25:00",
        "status_info": "Lead funnel review completed with follow-up actions.",
        "todays_task": "2026-05-09",
        "project_name": "general",
        "type": "task",
    },
    {
        "title": "Stabilize ERP staging deployment script",
        "description": "Fix database migration ordering and backup step in staging deployment script.",
        "status": "completed",
        "scheduled_date": "2026-05-18 09:30:00",
        "due_date": "2026-05-27 18:00:00",
        "priority": "high",
        "assignee": "sreedhanya",
        "created_by": "roshna",
        "completed_at": "2026-05-26 19:00:00",
        "status_info": "Staging deploy script now restores cleanly after rollback.",
        "todays_task": "2026-05-22",
        "project_name": "eOffice - ERP",
        "type": "task",
    },
    {
        "title": "Integrate device-room sync in Android app",
        "description": "Connect room assignment changes with backend sync and local cache refresh.",
        "status": "in_progress",
        "scheduled_date": "2026-06-01 09:45:00",
        "due_date": "2026-06-18 18:00:00",
        "priority": "high",
        "assignee": "visakh",
        "created_by": "roshna",
        "completed_at": None,
        "status_info": "API sync done; edge-case testing still pending.",
        "todays_task": "2026-06-15",
        "project_name": "Android Smart Home",
        "type": "task",
    },
    {
        "title": "Prepare production readiness review for gate controller",
        "description": "Summarize open hardware risks, vendor lead times, and bench validation results.",
        "status": "in_progress",
        "scheduled_date": "2026-06-09 10:00:00",
        "due_date": "2026-06-28 18:00:00",
        "priority": "high",
        "assignee": "jalan",
        "created_by": "arshadev",
        "completed_at": None,
        "status_info": "Waiting for final controller PCB observations.",
        "todays_task": "2026-06-21",
        "project_name": "eGate Development",
        "type": "task",
    },
    {
        "title": "Draft Q2 customer support improvement plan",
        "description": "Create action plan for installation support response time and escalation clarity.",
        "status": "in_progress",
        "scheduled_date": "2026-06-12 11:00:00",
        "due_date": "2026-06-30 18:00:00",
        "priority": "medium",
        "assignee": "sumesh",
        "created_by": "bijumon",
        "completed_at": None,
        "status_info": "Root-cause list prepared; staffing actions pending.",
        "todays_task": "2026-06-26",
        "project_name": "general",
        "type": "task",
    },
    {
        "title": "Close purchase approval pending edge cases",
        "description": "Resolve mismatched statuses and stale approver assignment edge cases in ERP workflow.",
        "status": "open",
        "scheduled_date": "2026-06-24 09:30:00",
        "due_date": "2026-07-04 17:30:00",
        "priority": "high",
        "assignee": "roshna",
        "created_by": "bijumon",
        "completed_at": None,
        "status_info": "Pending final fix list from QA.",
        "todays_task": "2026-07-03",
        "project_name": "eOffice - ERP",
        "type": "issue",
    },
    {
        "title": "Verify smart-home July demo build",
        "description": "Run final pre-demo validation on onboarding, room sync, and alert flows.",
        "status": "open",
        "scheduled_date": "2026-07-01 09:30:00",
        "due_date": "2026-07-04 16:00:00",
        "priority": "high",
        "assignee": "visakh",
        "created_by": "roshna",
        "completed_at": None,
        "status_info": "Blocked on one notification retry issue.",
        "todays_task": "2026-07-04",
        "project_name": "Android Smart Home",
        "type": "task",
    },
)

TASK_NOTES = (
    ("Prepare gate controller prototype BOM", "Vendor confirmed lead time for controller PCB assembly is 9 working days.", "Arshadev", "2026-01-21 16:20:00", 1),
    ("Map purchase workflow for ERP approvals", "Added manager escalation and cancellation path to workflow notes.", "Roshna", "2026-02-23 14:10:00", 1),
    ("Implement leave approval timeline UI", "Need one more validation pass for notification timestamps.", "SreeDhanya", "2026-04-12 18:05:00", 0),
    ("Integrate device-room sync in Android app", "Observed duplicate room refresh after reconnect; patch under review.", "Visakh", "2026-06-16 17:40:00", 1),
    ("Close purchase approval pending edge cases", "QA reported stale current approver row after cancellation path.", "Roshna", "2026-07-03 16:10:00", 1),
)

DAILY_TASKS = (
    ("sreedhanya", "Finalize employee master schema checks", "Validated employee master form behavior and mandatory fields.", 5.5, "completed", "2026-01-14 18:10:00", "2026-01-14", "2026-01-14 18:10:00", "Finalize employee master and attendance rules", "eOffice - ERP"),
    ("arshadev", "Review prototype BOM vendors", "Compared controller PCB, relay, and enclosure vendors for lead time.", 4.5, "completed", "2026-01-22 17:45:00", "2026-01-22", "2026-01-22 17:45:00", "Prepare gate controller prototype BOM", "eGate Development"),
    ("visakh", "Sketch onboarding sequence", "Prepared first-pass smart-home onboarding flow and room-link screens.", 5.0, "completed", "2026-02-08 17:50:00", "2026-02-08", "2026-02-08 17:50:00", "Create smart-home app onboarding wireframes", "Android Smart Home"),
    ("roshna", "Define purchase approval states", "Documented request, approval, rejection, and cancellation states.", 6.0, "completed", "2026-02-24 18:05:00", "2026-02-24", "2026-02-24 18:05:00", "Map purchase workflow for ERP approvals", "eOffice - ERP"),
    ("jalan", "Inspect motor mount revision", "Bench-fit tested revised mount on sliding gate assembly.", 5.0, "completed", "2026-03-05 17:30:00", "2026-03-05", "2026-03-05 17:30:00", "Validate gate motor mount fitment", "eGate Development"),
    ("visakh", "Set notification edge cases", "Expanded QA matrix for device offline and retry scenarios.", 4.0, "completed", "2026-03-19 18:00:00", "2026-03-19", "2026-03-19 18:00:00", "Set up Android beta notification test matrix", "Android Smart Home"),
    ("sumesh", "Summarize March support issues", "Grouped top recurring support incidents and response delays.", 4.5, "completed", "2026-03-28 17:40:00", "2026-03-28", "2026-03-28 17:40:00", "Create March support issue summary", "general"),
    ("sreedhanya", "Build leave timeline cards", "Implemented approval timeline cards and event ordering.", 5.5, "completed", "2026-04-11 18:20:00", "2026-04-11", "2026-04-11 18:20:00", "Implement leave approval timeline UI", "eOffice - ERP"),
    ("sumesh", "Revise installation checklist", "Added wiring safety and handover sign-off steps.", 5.0, "completed", "2026-04-14 17:55:00", "2026-04-14", "2026-04-14 17:55:00", "Prepare field installation checklist v2", "eGate Development"),
    ("nissar", "Review lead funnel", "Checked campaign response lag and proposal turnaround.", 3.5, "completed", "2026-05-09 17:10:00", "2026-05-09", "2026-05-09 17:10:00", "Review June marketing follow-up funnel", "general"),
    ("sreedhanya", "Stabilize deploy rollback", "Fixed migration ordering issue in ERP staging deploy script.", 6.0, "completed", "2026-05-22 18:35:00", "2026-05-22", "2026-05-22 18:35:00", "Stabilize ERP staging deployment script", "eOffice - ERP"),
    ("visakh", "Sync room assignment API", "Completed room assignment sync and local cache refresh path.", 5.5, "in_progress", "2026-06-15 18:10:00", "2026-06-15", None, "Integrate device-room sync in Android app", "Android Smart Home"),
    ("jalan", "Compile production review notes", "Captured vendor lead time and bench observation updates.", 4.0, "in_progress", "2026-06-21 17:40:00", "2026-06-21", None, "Prepare production readiness review for gate controller", "eGate Development"),
    ("sumesh", "Draft support improvement actions", "Outlined escalation clarity and installation support response improvements.", 3.5, "in_progress", "2026-06-26 17:20:00", "2026-06-26", None, "Draft Q2 customer support improvement plan", "general"),
    ("roshna", "List pending purchase workflow bugs", "Collected stale approver and duplicate status edge cases.", 4.5, "pending", "2026-07-03 18:00:00", "2026-07-03", None, "Close purchase approval pending edge cases", "eOffice - ERP"),
    ("visakh", "Run July demo build sanity pass", "Validated onboarding, room sync, and alert behavior before demo freeze.", 5.0, "pending", "2026-07-04 15:30:00", "2026-07-04", None, "Verify smart-home July demo build", "Android Smart Home"),
    ("dipin", "Update vendor file register", "Sorted purchase quotations and updated office vendor register.", 2.5, "completed", "2026-06-18 16:00:00", "2026-06-18", "2026-06-18 16:00:00", None, "general"),
    ("bijumon", "Review weekly cross-team blockers", "Reviewed top engineering and operations blockers with leads.", 2.0, "completed", "2026-06-30 19:00:00", "2026-06-30", "2026-06-30 19:00:00", None, "general"),
)

WORK_DIARY_ENTRIES = (
    ("sreedhanya", "2026-01-14", "Validated employee master fields and noted two missing department edge cases in ERP onboarding.", "eOffice - ERP"),
    ("arshadev", "2026-01-22", "Closed BOM comparison for controller board, receiver, and enclosure vendors. Shared final shortlist.", "eGate Development"),
    ("dipin", "2026-01-29", "Updated office admin register, toner stock, and filing material summary after monthly purchase.", "general"),
    ("visakh", "2026-02-08", "Completed onboarding wireframe draft and shared room assignment flow comments with Roshna.", "Android Smart Home"),
    ("roshna", "2026-02-24", "Documented purchase approval states and aligned edge cases with ERP workflow expectations.", "eOffice - ERP"),
    ("jalan", "2026-03-05", "Finished motor mount fitment check on both sample gates and marked minor bracket adjustment.", "eGate Development"),
    ("sreedhanya", "2026-03-18", "Reviewed leave workflow dependencies and prepared notes for timeline UI work.", "eOffice - ERP"),
    ("visakh", "2026-03-19", "Expanded notification QA scenarios for reconnect and offline alert sync.", "Android Smart Home"),
    ("sumesh", "2026-03-28", "Consolidated recurring service issues and field replacement part delays for monthly summary.", "general"),
    ("roshna", "2026-04-11", "Tested leave timeline UI ordering and flagged notification timestamps for one more pass.", "eOffice - ERP"),
    ("sumesh", "2026-04-14", "Updated installation checklist with safety confirmation and customer handover steps.", "eGate Development"),
    ("visakh", "2026-04-23", "Tracked Android room control bug with intermittent refresh lag after device reconnect.", "Android Smart Home"),
    ("nissar", "2026-05-09", "Reviewed lead follow-up funnel and highlighted delays between demo and quotation stages.", "general"),
    ("sreedhanya", "2026-05-22", "Fixed staging deployment rollback issue and retested DB migration sequence.", "eOffice - ERP"),
    ("arshadev", "2026-05-27", "Bench-tested latest controller board revision and noted stable relay timing behavior.", "eGate Development"),
    ("sumesh", "2026-06-04", "Prepared support toolkit replenishment list and identified missing connector crimp tools.", "general"),
    ("visakh", "2026-06-15", "Completed device-room sync API hook. Still need to resolve duplicate refresh after reconnect.", "Android Smart Home"),
    ("jalan", "2026-06-21", "Collected vendor lead-time updates and production readiness open points for controller release.", "eGate Development"),
    ("dipin", "2026-06-22", "Updated office inventory after internet backup router and pantry stock purchase.", "general"),
    ("sumesh", "2026-06-26", "Drafted improvement actions for support escalation clarity and installer response expectations.", "general"),
    ("bijumon", "2026-06-30", "Reviewed cross-team blockers with software, production, and support leads before July plan freeze.", "general"),
    ("roshna", "2026-07-03", "Prepared final bug list for purchase approval edge cases and assigned follow-up checks.", "eOffice - ERP"),
    ("visakh", "2026-07-04", "Ran demo-build sanity checks and logged one pending notification retry issue for follow-up.", "Android Smart Home"),
)

PROJECT_NOTES = (
    ("eOffice - ERP", "weekly_status", "ERP January week 3 update", "Employee master validation is complete. Purchase and leave workflow details have been mapped for implementation planning.", "roshna", "2026-01-12", "2026-01-18", "2026-01-18 18:15:00"),
    ("eGate Development", "normal", "Controller BOM decision log", "Selected preferred vendors for PCB assembly, enclosures, and receiver kits after comparing lead time and support responsiveness.", "arshadev", None, None, "2026-01-24 17:00:00"),
    ("Android Smart Home", "weekly_status", "Smart-home February sprint summary", "Onboarding flow and room assignment wireframes were approved. Initial QA coverage for notifications has been drafted.", "roshna", "2026-02-09", "2026-02-15", "2026-02-15 18:05:00"),
    ("eOffice - ERP", "normal", "Purchase workflow functional note", "Approval, rejection, and cancellation states are aligned. Remaining work is in UI timeline representation and stale approver handling.", "roshna", None, None, "2026-02-26 18:20:00"),
    ("general", "weekly_status", "Support and admin March operations note", "Support issue grouping is now available for monthly review, and admin purchases are being tracked with cleaner categories.", "bijumon", "2026-03-23", "2026-03-29", "2026-03-29 18:00:00"),
    ("eGate Development", "weekly_status", "April installation readiness update", "Installation checklist v2 is ready. Prototype hardware fitment issues are resolved, but production-readiness review remains open.", "arshadev", "2026-04-13", "2026-04-19", "2026-04-19 17:45:00"),
    ("eOffice - ERP", "weekly_status", "May deployment stability summary", "Staging deployment reliability improved after fixing rollback ordering. Purchase and leave flows are stable in test passes.", "roshna", "2026-05-18", "2026-05-24", "2026-05-24 18:30:00"),
    ("Android Smart Home", "weekly_status", "June smart-home integration status", "Device-room sync is functionally complete. Remaining work is duplicate refresh handling and July demo hardening.", "roshna", "2026-06-15", "2026-06-21", "2026-06-21 18:10:00"),
    ("general", "normal", "July kickoff leadership note", "Cross-team blockers were reviewed before July planning. Key attention areas are ERP approval edge cases and Android demo-build stability.", "bijumon", None, None, "2026-07-03 19:00:00"),
)

PROJECT_MEMORIES = (
    ("eOffice - ERP", "2026-02-28", "weekly_summary", "ERP workflow scope now covers employee master, leave approval visibility, and purchase approval state handling.", "Derived from January and February project notes."),
    ("eGate Development", "2026-04-30", "weekly_summary", "eGate controller and installation readiness improved through BOM finalization, fitment validation, and revised field checklist.", "Derived from BOM log and April readiness note."),
    ("Android Smart Home", "2026-06-30", "weekly_summary", "Android Smart Home is nearing demo readiness. Room sync is integrated, but notification retry and duplicate refresh need cleanup.", "Derived from sprint and June status notes."),
    ("general", "2026-06-30", "weekly_summary", "Operations data now shows clearer support trends, admin purchase traceability, and lead follow-up review points.", "Derived from support/admin notes and leadership review."),
)

PROJECT_FILES = (
    ("eOffice - ERP", r"projects\eoffice\docs\employee-master-validation-checklist-v1.docx", "employee-master-validation-checklist-v1.docx", "docx", 84216, "HR and employee master validation checklist for ERP rollout."),
    ("eOffice - ERP", r"projects\eoffice\reports\purchase-workflow-state-map.pdf", "purchase-workflow-state-map.pdf", "pdf", 126540, "Purchase workflow state and approver transition map."),
    ("eGate Development", r"projects\egate\docs\controller-bom-revA.xlsx", "controller-bom-revA.xlsx", "xlsx", 65312, "Revision A BOM for eGate controller prototype batch."),
    ("eGate Development", r"projects\egate\docs\installation-checklist-v2.pdf", "installation-checklist-v2.pdf", "pdf", 90448, "Field installation checklist version 2."),
    ("Android Smart Home", r"projects\android-smart-home\ui\onboarding-wireframes-v1.fig", "onboarding-wireframes-v1.fig", "fig", 44320, "Initial onboarding and room assignment wireframes."),
    ("Android Smart Home", r"projects\android-smart-home\reports\july-demo-sanity-report.xlsx", "july-demo-sanity-report.xlsx", "xlsx", 58816, "Pre-demo sanity validation report."),
    ("general", r"operations\support\march-support-summary.pdf", "march-support-summary.pdf", "pdf", 71240, "March support summary for leadership review."),
    ("general", r"operations\admin\vendor-register-2026.xlsx", "vendor-register-2026.xlsx", "xlsx", 53248, "Office vendor and quotation tracking register."),
)

PROJECT_FACTS = (
    ("eOffice - ERP", "2026-05-24", "owner", "Who leads ERP delivery?", "Roshna leads ERP delivery and sprint coordination.", "Roshna", "weekly status and deployment review", None),
    ("eGate Development", "2026-04-19", "hardware_status", "What is the main eGate hardware focus?", "The main focus is controller readiness, vendor lead time control, and installation checklist quality.", "Arshadev", "BOM and readiness notes", None),
    ("Android Smart Home", "2026-06-21", "implementation", "Who owns Android Smart Home implementation?", "Visakh owns Android feature delivery, with Roshna overseeing delivery and Arshadev advising on IoT integration.", "Visakh", "June integration status note", None),
    ("general", "2026-06-30", "operations", "What are the main cross-team blockers entering July?", "The top blockers are ERP approval edge cases, Android demo-build stability, and closing production readiness observations.", "Bijumon", "July leadership note", None),
)


def copy_blank_db(force: bool) -> None:
    if not BLANK_DB.exists():
        raise FileNotFoundError(f"Blank database not found: {BLANK_DB}")
    if TARGET_DB.exists():
        if not force:
            raise FileExistsError(f"Target database already exists: {TARGET_DB}")
        TARGET_DB.unlink()
    shutil.copy2(BLANK_DB, TARGET_DB)


def connect_db() -> sqlite3.Connection:
    conn = sqlite3.connect(TARGET_DB)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def upsert_department(cur: sqlite3.Cursor, department_name: str) -> int:
    cur.execute("SELECT departmentID FROM Departments WHERE department_name = ?", (department_name,))
    row = cur.fetchone()
    if row:
        return int(row["departmentID"])
    cur.execute("INSERT INTO Departments (department_name) VALUES (?)", (department_name,))
    return int(cur.lastrowid)


def upsert_expense_category(cur: sqlite3.Cursor, name: str, description: str) -> int:
    cur.execute("SELECT id FROM ExpenseCategories WHERE name = ?", (name,))
    row = cur.fetchone()
    if row:
        cur.execute("UPDATE ExpenseCategories SET description = ? WHERE id = ?", (description, row["id"]))
        return int(row["id"])
    cur.execute(
        "INSERT INTO ExpenseCategories (name, description) VALUES (?, ?)",
        (name, description),
    )
    return int(cur.lastrowid)


def upsert_user(cur: sqlite3.Cursor, seed: UserSeed, department_id: int) -> int:
    names = seed.full_name.split(" ", 1)
    first_name = names[0]
    last_name = names[1] if len(names) > 1 else ""
    cur.execute("SELECT id FROM Users WHERE username = ?", (seed.username,))
    row = cur.fetchone()
    values = (
        seed.email,
        seed.full_name,
        seed.department,
        seed.leave_balance,
        1,
        SEED_DATE,
        first_name,
        last_name,
        seed.shift_id,
        seed.role_id,
        "active",
        department_id,
        seed.mobile,
        seed.mobile,
        "",
        seed.role_name,
        "Regular shift" if seed.shift_id == 1 else "Regular-Late",
        seed.mobile,
        seed.is_admin,
        0,
        SEED_DATE,
        seed.username,
        f"seeded::{seed.username}",
        None,
        SEED_DATE,
    )
    if row:
        cur.execute(
            """
            UPDATE Users
            SET email=?, full_name=?, department=?, leave_balance=?, is_active=?, registration_timestamp=?,
                FirstName=?, LastName=?, shiftID=?, role_id=?, status=?, department_id=?, mobile_number=?,
                whatsapp_number=?, telegram_chat_id=?, role=?, shift=?, WhatsapID=?, is_admin=?,
                force_password_change=?, password_updated_at=?, username=?, password_hash=?, last_login=?, created_at=?
            WHERE id=?
            """,
            values + (row["id"],),
        )
        return int(row["id"])
    cur.execute(
        """
        INSERT INTO Users (
            email, full_name, department, leave_balance, is_active, registration_timestamp,
            FirstName, LastName, shiftID, role_id, status, department_id, mobile_number,
            whatsapp_number, telegram_chat_id, role, shift, WhatsapID, is_admin,
            force_password_change, password_updated_at, username, password_hash, last_login, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        values,
    )
    return int(cur.lastrowid)


def upsert_employee(
    cur: sqlite3.Cursor,
    seed: UserSeed,
    department_id: int,
    linked_user_id: int,
    manager_employee_id: int | None,
) -> int:
    cur.execute("SELECT id FROM Employees WHERE linked_user_id = ?", (linked_user_id,))
    row = cur.fetchone()
    values = (
        f"EBI-{linked_user_id:03d}",
        seed.full_name,
        f"{seed.department} Quarters, Kochi",
        "Thrippunithura, Kochi",
        seed.mobile,
        seed.official_email,
        seed.personal_email,
        "active",
        seed.join_date,
        department_id,
        seed.designation,
        manager_employee_id,
        linked_user_id,
        SEED_DATE,
        SEED_DATE,
    )
    if row:
        cur.execute(
            """
            UPDATE Employees
            SET employee_code=?, full_name=?, permanent_address=?, local_address=?, mobile_number=?,
                official_email=?, personal_email=?, employment_status=?, join_date=?, department_id=?,
                designation=?, manager_employee_id=?, linked_user_id=?, created_at=?, updated_at=?
            WHERE id=?
            """,
            values + (row["id"],),
        )
        return int(row["id"])
    cur.execute(
        """
        INSERT INTO Employees (
            employee_code, full_name, permanent_address, local_address, mobile_number,
            official_email, personal_email, employment_status, join_date, department_id,
            designation, manager_employee_id, linked_user_id, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        values,
    )
    return int(cur.lastrowid)


def upsert_emergency_contacts(cur: sqlite3.Cursor, employee_id: int, seed: UserSeed) -> None:
    cur.execute("SELECT id FROM EmployeeEmergencyContacts WHERE employee_id = ?", (employee_id,))
    row = cur.fetchone()
    values = (
        employee_id,
        seed.emergency_parent,
        seed.emergency_spouse,
        None,
        SEED_DATE,
        SEED_DATE,
    )
    if row:
        cur.execute(
            """
            UPDATE EmployeeEmergencyContacts
            SET employee_id=?, emergency_contact_parent=?, emergency_contact_spouse=?,
                emergency_contact_child=?, created_at=?, updated_at=?
            WHERE id=?
            """,
            values + (row["id"],),
        )
        return
    cur.execute(
        """
        INSERT INTO EmployeeEmergencyContacts (
            employee_id, emergency_contact_parent, emergency_contact_spouse,
            emergency_contact_child, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        values,
    )


def replace_employee_skills(cur: sqlite3.Cursor, employee_id: int, seed: UserSeed) -> None:
    cur.execute(
        "DELETE FROM EmployeeDetails WHERE employee_id = ? AND category = 'skills'",
        (employee_id,),
    )
    for skill in seed.skill_tags:
        cur.execute(
            """
            INSERT INTO EmployeeDetails (
                employee_id, detail_key, detail_label, detail_type, detail_value_text,
                file_id, category, is_required, is_current, effective_date, created_at, updated_at
            ) VALUES (?, 'skill', 'Skill', 'text', ?, NULL, 'skills', 0, 1, ?, ?, ?)
            """,
            (employee_id, skill, seed.join_date, SEED_DATE, SEED_DATE),
        )


def upsert_project(cur: sqlite3.Cursor, project: dict[str, object]) -> int:
    cur.execute("SELECT id FROM Projects WHERE name = ?", (project["name"],))
    row = cur.fetchone()
    values = (
        project["budget_limit"],
        project["current_spending"],
        project["status"],
        project["description"],
        project["startDate"],
        project["endDate"],
    )
    if row:
        cur.execute(
            """
            UPDATE Projects
            SET budget_limit=?, current_spending=?, status=?, description=?, startDate=?, endDate=?
            WHERE id=?
            """,
            values + (row["id"],),
        )
        return int(row["id"])
    cur.execute(
        """
        INSERT INTO Projects (name, budget_limit, current_spending, status, description, startDate, endDate)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (project["name"],) + values,
    )
    return int(cur.lastrowid)


def replace_project_members(
    cur: sqlite3.Cursor,
    project_id: int,
    member_specs: tuple[tuple[str, str], ...],
    user_map: dict[str, int],
) -> None:
    cur.execute("DELETE FROM ProjectMembers WHERE project_id = ?", (project_id,))
    for username, member_role in member_specs:
        user_id = user_map[username]
        cur.execute(
            """
            INSERT INTO ProjectMembers (
                project_id, user_id, member_role, allocation_status, added_by_user_id, created_at, updated_at
            ) VALUES (?, ?, ?, 'active', 1, ?, ?)
            """,
            (project_id, user_id, member_role, SEED_DATE, SEED_DATE),
        )


def seed_product_catalog(cur: sqlite3.Cursor, general_project_id: int) -> None:
    cur.execute(
        "DELETE FROM ProjectKnowledgeFacts WHERE project_id = ? AND fact_type = 'product_catalog'",
        (general_project_id,),
    )
    for product_name, answer_text in PRODUCT_FACTS:
        cur.execute(
            """
            INSERT INTO ProjectKnowledgeFacts (
                project_id, fact_date, fact_type, subject, answer_text, person_name,
                source_type, source_id, evidence_summary, created_at, updated_at
            ) VALUES (?, '2026-01-05', 'product_catalog', ?, ?, 'Ebird Innovation',
                      'seed_script', NULL, 'Seeded fictional product catalog entry', ?, ?)
            """,
            (general_project_id, product_name, answer_text, SEED_DATE, SEED_DATE),
        )


def seed_holidays(cur: sqlite3.Cursor) -> None:
    cur.execute("DELETE FROM HolidayList")
    for holiday_date, holiday_name, holiday_type, description, is_optional in HOLIDAYS:
        cur.execute(
            """
            INSERT INTO HolidayList (
                holiday_date, holiday_name, holiday_type, description,
                is_optional, created_by, updated_by, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, 1, 1, ?, ?)
            """,
            (holiday_date, holiday_name, holiday_type, description, is_optional, SEED_DATE, SEED_DATE),
        )


def seed_leave_requests(
    cur: sqlite3.Cursor,
    employee_ids: dict[str, int],
    user_ids: dict[str, int],
    manager_employee_ids: dict[str, int | None],
    manager_user_ids: dict[str, int | None],
) -> None:
    cur.execute("DELETE FROM LeaveRequests")
    for item in LEAVE_REQUESTS:
        username = item["username"]
        cur.execute(
            """
            INSERT INTO LeaveRequests (
                employee_id, manager_employee_id, manager_user_id, leave_type,
                start_date, end_date, requested_days, reason, medical_certificate_ref,
                request_channel, request_message, status, manager_decision_note,
                submitted_at, approved_at, rejected_at, cancelled_at,
                team_notified_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                employee_ids[username],
                manager_employee_ids[username],
                manager_user_ids[username],
                item["leave_type"],
                item["start_date"],
                item["end_date"],
                item["requested_days"],
                item["reason"],
                None,
                item["request_channel"],
                item["request_message"],
                item["status"],
                item["manager_decision_note"],
                item["submitted_at"],
                item["approved_at"],
                item["rejected_at"],
                item["cancelled_at"],
                item["team_notified_at"],
                item["submitted_at"],
                item["submitted_at"],
            ),
        )


def seed_expenses(
    cur: sqlite3.Cursor,
    category_ids: dict[str, int],
    project_ids: dict[str, int],
    user_ids: dict[str, int],
) -> None:
    cur.execute("DELETE FROM Expenses")
    for expense_date, category_name, project_name, description, vendor, amount, entered_by, purchased_by, status in EXPENSES:
        project_id = project_ids[project_name]
        cur.execute(
            """
            INSERT INTO Expenses (
                file_id, amount, currency, expense_date, entry_date, description, vendor,
                category_id, project_id, entered_by_user_id, purchased_by_user_id, status, is_manual_entry
            ) VALUES (NULL, ?, 'INR', ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            """,
            (
                amount,
                expense_date,
                f"{expense_date} 12:00:00",
                description,
                vendor,
                category_ids[category_name],
                project_id,
                user_ids[entered_by],
                user_ids[purchased_by],
                status,
            ),
        )


def seed_purchase_requests(
    cur: sqlite3.Cursor,
    project_ids: dict[str, int],
    user_ids: dict[str, int],
) -> None:
    cur.execute("DELETE FROM PurchaseApprovalActions")
    cur.execute("DELETE FROM PurchaseRequests")
    for item in PURCHASE_REQUESTS:
        project_id = project_ids[item["project_name"]] if item["project_name"] else None
        manager_user_id = user_ids[item["manager"]] if item["manager"] else None
        current_approver_user_id = user_ids[item["current_approver"]] if item["current_approver"] else None
        cur.execute(
            """
            INSERT INTO PurchaseRequests (
                requester_user_id, title, description, amount, currency, justification,
                project_scope, project_id, file_id, status, manager_user_id, current_approver_user_id,
                decision_note, request_channel, approved_at, rejected_at, cancelled_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, 'INR', ?, ?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_ids[item["requester"]],
                item["title"],
                item["description"],
                item["amount"],
                item["justification"],
                item["project_scope"],
                project_id,
                item["status"],
                manager_user_id,
                current_approver_user_id,
                item["decision_note"],
                item["request_channel"],
                item["approved_at"],
                item["rejected_at"],
                item["cancelled_at"],
                item["created_at"],
                item["created_at"],
            ),
        )
        request_id = int(cur.lastrowid)
        for actor, action_type, action_channel, action_note, forwarded_to, created_at in item["actions"]:
            forwarded_to_user_id = user_ids[forwarded_to] if forwarded_to else None
            cur.execute(
                """
                INSERT INTO PurchaseApprovalActions (
                    purchase_request_id, actor_user_id, action_type, action_channel,
                    action_note, forwarded_to_user_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    request_id,
                    user_ids[actor],
                    action_type,
                    action_channel,
                    action_note,
                    forwarded_to_user_id,
                    created_at,
                ),
            )


def seed_tasks(cur: sqlite3.Cursor, project_ids: dict[str, int], user_ids: dict[str, int]) -> dict[str, int]:
    cur.execute("DELETE FROM TaskNotes")
    cur.execute("DELETE FROM DailyTasks")
    cur.execute("DELETE FROM Tasks")
    task_ids: dict[str, int] = {}
    for item in TASKS:
        assignee_id = user_ids[item["assignee"]]
        creator_id = user_ids[item["created_by"]]
        cur.execute(
            """
            INSERT INTO Tasks (
                title, description, status, scheduled_date, due_date, priority, assigned_to,
                created_by, created_at, updated_at, completed_at, is_active, assigned_to_id,
                created_by_id, status_info, todays_task, ProjectID, type
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?)
            """,
            (
                item["title"],
                item["description"],
                item["status"],
                item["scheduled_date"],
                item["due_date"],
                item["priority"],
                assignee_id,
                item["created_by"],
                item["scheduled_date"],
                item["completed_at"] or item["scheduled_date"],
                item["completed_at"],
                assignee_id,
                creator_id,
                item["status_info"],
                item["todays_task"],
                project_ids[item["project_name"]],
                item["type"],
            ),
        )
        task_ids[item["title"]] = int(cur.lastrowid)
    for title, note_content, created_by, created_at, is_internal in TASK_NOTES:
        cur.execute(
            """
            INSERT INTO TaskNotes (task_id, note_content, created_by, created_at, is_internal)
            VALUES (?, ?, ?, ?, ?)
            """,
            (task_ids[title], note_content, created_by, created_at, is_internal),
        )
    return task_ids


def seed_daily_tasks(cur: sqlite3.Cursor, task_ids: dict[str, int], project_ids: dict[str, int], user_ids: dict[str, int]) -> None:
    cur.execute("DELETE FROM DailyTasks")
    for username, task, description, hours_spend, status, date_created, marked_for_today, closed_date, linked_task_title, project_name in DAILY_TASKS:
        linked_task_id = task_ids.get(linked_task_title) if linked_task_title else None
        project_id = project_ids[project_name]
        cur.execute(
            """
            INSERT INTO DailyTasks (
                user_id, task, description, hours_spend, status, date_created,
                marked_for_today, closed_date, linked_task_id, project_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(user_ids[username]),
                task,
                description,
                hours_spend,
                status,
                date_created,
                marked_for_today,
                closed_date,
                linked_task_id,
                project_id,
            ),
        )


def seed_work_diary_entries(cur: sqlite3.Cursor, project_ids: dict[str, int], user_ids: dict[str, int]) -> None:
    cur.execute("DELETE FROM WorkDiaryEntries")
    for username, entry_date, note_text, project_name in WORK_DIARY_ENTRIES:
        cur.execute(
            """
            INSERT INTO WorkDiaryEntries (
                user_id, entry_date, note_text, project_id, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                str(user_ids[username]),
                entry_date,
                note_text,
                project_ids[project_name],
                f"{entry_date} 18:00:00",
                f"{entry_date} 18:00:00",
            ),
        )


def seed_project_notes(cur: sqlite3.Cursor, project_ids: dict[str, int], user_ids: dict[str, int]) -> None:
    cur.execute("DELETE FROM ProjectNotes")
    for project_name, note_type, title, content, author_username, week_start, week_end, created_at in PROJECT_NOTES:
        cur.execute(
            """
            INSERT INTO ProjectNotes (
                project_id, note_type, title, content, author_user_id, author_name,
                week_start, week_end, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                project_ids[project_name],
                note_type,
                title,
                content,
                user_ids[author_username],
                author_username.capitalize() if author_username != "sreedhanya" else "SreeDhanya",
                week_start,
                week_end,
                created_at,
                created_at,
            ),
        )


def seed_project_memories(cur: sqlite3.Cursor, project_ids: dict[str, int]) -> None:
    cur.execute("DELETE FROM ProjectMemory")
    for project_name, memory_date, memory_type, content, source_summary in PROJECT_MEMORIES:
        cur.execute(
            """
            INSERT INTO ProjectMemory (
                project_id, memory_date, memory_type, content, source_summary, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                project_ids[project_name],
                memory_date,
                memory_type,
                content,
                source_summary,
                f"{memory_date} 18:30:00",
                f"{memory_date} 18:30:00",
            ),
        )


def seed_files(cur: sqlite3.Cursor, project_ids: dict[str, int]) -> None:
    cur.execute("DELETE FROM Files")
    for project_name, file_path, filename, file_type, file_size, description in PROJECT_FILES:
        cur.execute(
            """
            INSERT INTO Files (
                file_path, filename, file_type, file_size, file_hash, upload_date, description, task_id, note_id, project_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?)
            """,
            (
                file_path,
                filename,
                file_type,
                file_size,
                f"seedhash::{filename}",
                SEED_DATE,
                description,
                project_ids[project_name],
            ),
        )


def seed_project_facts(cur: sqlite3.Cursor, project_ids: dict[str, int]) -> None:
    cur.execute("DELETE FROM ProjectKnowledgeFacts WHERE source_type = 'seed_script' AND fact_type != 'product_catalog'")
    for project_name, fact_date, fact_type, subject, answer_text, person_name, evidence_summary, source_id in PROJECT_FACTS:
        cur.execute(
            """
            INSERT INTO ProjectKnowledgeFacts (
                project_id, fact_date, fact_type, subject, answer_text, person_name,
                source_type, source_id, evidence_summary, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, 'seed_script', ?, ?, ?, ?)
            """,
            (
                project_ids[project_name],
                fact_date,
                fact_type,
                subject,
                answer_text,
                person_name,
                source_id,
                evidence_summary,
                f"{fact_date} 19:00:00",
                f"{fact_date} 19:00:00",
            ),
        )


def seed_foundation() -> None:
    conn = connect_db()
    cur = conn.cursor()

    department_ids = {name: upsert_department(cur, name) for name in DEPARTMENTS}
    category_ids = {name: upsert_expense_category(cur, name, description) for name, description in EXPENSE_CATEGORIES}

    user_ids: dict[str, int] = {}
    for seed in USERS:
        user_ids[seed.username] = upsert_user(cur, seed, department_ids[seed.department])

    employee_ids: dict[str, int] = {}
    for seed in USERS:
        manager_employee_id = employee_ids.get(seed.manager_username) if seed.manager_username else None
        employee_id = upsert_employee(
            cur,
            seed,
            department_ids[seed.department],
            user_ids[seed.username],
            manager_employee_id,
        )
        employee_ids[seed.username] = employee_id
        upsert_emergency_contacts(cur, employee_id, seed)
        replace_employee_skills(cur, employee_id, seed)

    manager_employee_ids = {
        seed.username: (employee_ids.get(seed.manager_username) if seed.manager_username else None)
        for seed in USERS
    }
    manager_user_ids = {
        seed.username: (user_ids.get(seed.manager_username) if seed.manager_username else None)
        for seed in USERS
    }

    project_ids: dict[str, int] = {}
    for name in ("OASIS", "general"):
        cur.execute("SELECT id FROM Projects WHERE name = ?", (name,))
        row = cur.fetchone()
        if row:
            project_ids[name] = int(row["id"])
    for project in PROJECTS:
        project_ids[project["name"]] = upsert_project(cur, project)

    for project_name, members in PROJECT_MEMBERS.items():
        replace_project_members(cur, project_ids[project_name], members, user_ids)

    cur.execute("SELECT id FROM Projects WHERE name = 'general'")
    general_project = cur.fetchone()
    if general_project:
        seed_product_catalog(cur, int(general_project["id"]))

    seed_holidays(cur)
    seed_leave_requests(cur, employee_ids, user_ids, manager_employee_ids, manager_user_ids)
    seed_expenses(cur, category_ids, project_ids, user_ids)
    seed_purchase_requests(cur, project_ids, user_ids)
    task_ids = seed_tasks(cur, project_ids, user_ids)
    seed_daily_tasks(cur, task_ids, project_ids, user_ids)
    seed_work_diary_entries(cur, project_ids, user_ids)
    seed_project_notes(cur, project_ids, user_ids)
    seed_project_memories(cur, project_ids)
    seed_files(cur, project_ids)
    seed_project_facts(cur, project_ids)

    conn.commit()
    conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed a fictional Ebird Innovation OASIS database.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite data/ebirdInno.db if it already exists.",
    )
    args = parser.parse_args()

    copy_blank_db(force=args.force)
    seed_foundation()
    print(f"Seeded foundational Ebird Innovation data into: {TARGET_DB}")


if __name__ == "__main__":
    main()
