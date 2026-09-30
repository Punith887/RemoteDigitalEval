import os
import sys
from pathlib import Path
from datetime import date, timedelta

# Ensure backend directory is in sys.path when running outside backend/
BASE_DIR = Path(__file__).resolve().parent.parent / "backend"
if BASE_DIR.exists() and str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "evaluation_core.settings")

import django
django.setup()

from django.utils import timezone
from django.contrib.auth.models import User
from apps.configuration.models import AcademicYear, ExamSession, Paper, Programme, Subject, Term, Regulation
from apps.tenancy.models import Institution, Membership, TenantAccount, TenantDomain
from apps.tenancy.services import DEFAULT_MODULES

user = User.objects.filter(username="admin@admiezo.local").first()

universities = [
    {
        "code": "vtu",
        "name": "Visvesvaraya Technological University",
        "slug": "vtu",
        "brand_name": "VTU - Visvesvaraya Technological University",
        "brand_description": "Belagavi, Karnataka - Central Evaluation System",
        "brand_theme": "ocean",
        "subdomains": [
            "vtu.admiezo.com",
            "vtu.192.168.1.55.nip.io",
            "vtu.localhost",
        ],
        "prog_code": "VTU-BE-CSE",
        "prog_name": "B.E. Computer Science and Engineering",
        "session_name": "VTU January 2026 Semester Examination",
        "subjects": [
            ("21CS51", "Management and Entrepreneurship", 5),
            ("21CS52", "Computer Networks and Security", 5),
            ("21CS53", "Database Management Systems", 5),
        ],
    },
    {
        "code": "gmit",
        "name": "GM Institute of Technology",
        "slug": "gmit",
        "brand_name": "GMIT - GM Institute of Technology",
        "brand_description": "Davangere, Karnataka - Digital Valuation Portal",
        "brand_theme": "ruby",
        "subdomains": [
            "gmit.admiezo.com",
            "gmit.192.168.1.55.nip.io",
            "gmit.localhost",
        ],
        "prog_code": "GMIT-BE-ISE",
        "prog_name": "B.E. Information Science and Engineering",
        "session_name": "GMIT December 2026 Semester Evaluation",
        "subjects": [
            ("18IS61", "File Structures and Storage", 6),
            ("18IS62", "Software Testing and Automation", 6),
            ("18IS63", "Web Technology Laboratory", 6),
        ],
    },
]

for uni in universities:
    inst, _ = Institution.objects.get_or_create(
        code=uni["code"],
        defaults={
            "name": uni["name"],
            "kind": Institution.Kind.UNIVERSITY,
            "policy": {"mfa_required": False, "session_minutes": 60},
        },
    )
    tenant_id = inst.tenant_id
    account, _ = TenantAccount.objects.get_or_create(
        root_institution=inst,
        defaults={
            "slug": uni["slug"],
            "status": TenantAccount.Status.ACTIVE,
            "plan": TenantAccount.Plan.ENTERPRISE,
            "enabled_modules": DEFAULT_MODULES,
            "brand_name": uni["brand_name"],
            "brand_description": uni["brand_description"],
            "brand_theme": uni["brand_theme"],
        },
    )
    account.status = TenantAccount.Status.ACTIVE
    account.brand_name = uni["brand_name"]
    account.brand_description = uni["brand_description"]
    account.brand_theme = uni["brand_theme"]
    account.enabled_modules = DEFAULT_MODULES
    account.save()

    for sub in uni["subdomains"]:
        dom, _ = TenantDomain.objects.get_or_create(
            hostname=sub,
            defaults={
                "tenant_account": account,
                "kind": TenantDomain.Kind.MANAGED,
                "status": TenantDomain.Status.ACTIVE,
                "is_primary": (sub == uni["subdomains"][0]),
                "verified_at": timezone.now(),
            },
        )
        dom.tenant_account = account
        dom.status = TenantDomain.Status.ACTIVE
        dom.save()

    if user:
        mem, _ = Membership.objects.get_or_create(
            user=user,
            institution=inst,
            defaults={
                "role": Membership.Role.UNIVERSITY_ADMIN,
                "permissions": ["*"],
                "enabled_modules": account.enabled_modules,
            },
        )
        mem.enabled_modules = account.enabled_modules
        mem.save()

    year, _ = AcademicYear.objects.get_or_create(
        tenant_id=tenant_id,
        label="2026-27",
        defaults={"starts_on": date(2026, 7, 1), "ends_on": date(2027, 6, 30)},
    )
    term, _ = Term.objects.get_or_create(
        tenant_id=tenant_id,
        academic_year=year,
        name="Odd semester",
        defaults={"sequence": 1, "starts_on": year.starts_on, "ends_on": year.ends_on},
    )
    session, _ = ExamSession.objects.get_or_create(
        tenant_id=tenant_id,
        academic_year=year,
        name=uni["session_name"],
        defaults={
            "term": "Odd semester",
            "term_record": term,
            "evaluation_starts_at": timezone.now() - timedelta(days=2),
            "evaluation_ends_at": timezone.now() + timedelta(days=30),
            "status": ExamSession.Status.ACTIVE,
        },
    )
    reg, _ = Regulation.objects.get_or_create(
        tenant_id=tenant_id,
        code=f"R-2026-{uni['code'].upper()}",
        defaults={"title": f"Regulation 2026 ({uni['code'].upper()})", "effective_from": date(2026, 1, 1)},
    )
    prog, _ = Programme.objects.get_or_create(
        tenant_id=tenant_id,
        code=uni["prog_code"],
        defaults={"name": uni["prog_name"], "regulation": reg.code, "regulation_record": reg},
    )
    for code, title, sem in uni["subjects"]:
        sub_obj, _ = Subject.objects.get_or_create(
            tenant_id=tenant_id,
            code=code,
            defaults={
                "name": title,
                "programme": prog,
                "semester": sem,
                "session_ids": [str(session.id)],
            },
        )
        Paper.objects.get_or_create(
            tenant_id=tenant_id,
            code=f"P-{code}",
            defaults={
                "session": session,
                "subject": sub_obj,
                "title": f"{title} Paper",
                "max_marks": 100,
                "pass_marks": 35,
                "status": Paper.Status.APPROVED,
            },
        )

print("SUCCESS: Provisioned VTU and GMIT successfully.")
