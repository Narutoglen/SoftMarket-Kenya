from datetime import datetime, timezone

from django.db import migrations, models


BLOG_POSTS = [
    {
        "title": "Why Kenyan Businesses Are Moving Away from Off-the-Shelf Software in 2024",
        "slug": "kenyan-businesses-moving-away-from-off-the-shelf-software-2024",
        "category": "Industry Trends",
        "author_name": "Amina Wanjiru",
        "author_role": "Head of Product",
        "published_at": datetime(2024, 3, 14, 9, 0, tzinfo=timezone.utc),
        "excerpt": (
            "Kenyan SMEs are reassessing dollar-priced SaaS tools and choosing local custom "
            "software where ownership, M-Pesa integration, and data residency matter."
        ),
        "body": (
            "There is a quiet but significant shift happening across Nairobi's boardrooms and "
            "Mombasa's trading floors. Business owners who once happily subscribed to "
            "international SaaS tools are now asking a different question: why am I paying in "
            "dollars for a product that was never designed for how we work?\n\n"
            "## 1. The currency problem\n\n"
            "Most global software tools price in USD or EUR. With the shilling under sustained "
            "pressure, a KES 12,000 monthly subscription in 2021 now costs closer to KES 20,000 "
            "for the same product. Custom software built locally is a capital investment - you "
            "pay once, and you own it.\n\n"
            "## 2. The localisation gap\n\n"
            "M-Pesa is the dominant payment rail for most Kenyan consumers. Yet many "
            "international platforms treat it as an afterthought, offering clunky plugins "
            "maintained by third parties. A custom-built system puts M-Pesa, Airtel Money, and "
            "bank integrations at the centre, not the edges.\n\n"
            "## 3. The compliance shift\n\n"
            "Kenya's Data Protection Act (2019) continues to mature. Off-the-shelf tools store "
            "your customer data on servers in Ireland or Virginia - a growing risk for regulated "
            "businesses. Local custom software can be built to keep data on Kenyan infrastructure "
            "from day one.\n\n"
            "None of this means every business should rush to build custom software. But the "
            "calculus has changed, and the developers capable of building it are no longer hard "
            "to find."
        ),
    },
    {
        "title": "The Silicon Savannah Is Maturing - Here Is What That Means for Software Buyers",
        "slug": "silicon-savannah-maturing-software-buyers",
        "category": "Developer Ecosystem",
        "author_name": "Brian Omondi",
        "author_role": "Senior Developer",
        "published_at": datetime(2024, 1, 22, 9, 0, tzinfo=timezone.utc),
        "excerpt": (
            "Kenya's developer market is no longer only aspirational. Remote-work experience, "
            "modern tooling, and stronger marketplace structures are changing what buyers can expect."
        ),
        "body": (
            "Kenya has been called the Silicon Savannah for over a decade, but for much of that "
            "time the label felt more aspirational than accurate. That has changed. The talent "
            "that spent the 2010s building skills on international platforms - Upwork, Toptal, "
            "remote contracts with European startups - is now increasingly turning its attention "
            "homeward.\n\n"
            "## 1. The remote work dividend\n\n"
            "The pandemic accelerated a shift that was already underway. Kenyan developers who "
            "spent three or four years working on complex systems for European and American "
            "clients came home with experience that previously only existed in Nairobi's largest "
            "tech firms. That expertise is now available to local SMEs for the first time.\n\n"
            "## 2. Frameworks and tooling have caught up\n\n"
            "A business that requested a custom system in 2015 would have waited six months and "
            "paid a premium for a basic CRUD application. Today, mature frameworks - Django, "
            "React, Flutter, FastAPI - combined with affordable cloud infrastructure mean a "
            "well-scoped project can be delivered in weeks, not quarters.\n\n"
            "## 3. The trust problem still exists\n\n"
            "Talent alone does not close deals. The persistent complaint from Kenyan business "
            "owners is not that local developers lack skill - it is that they lack accountability. "
            "Projects stall, scope creeps, and there is no formal mechanism for recourse. This is "
            "the gap that a structured marketplace is designed to close."
        ),
    },
    {
        "title": "Five Signs Your Business Has Outgrown Its Spreadsheets",
        "slug": "five-signs-your-business-has-outgrown-spreadsheets",
        "category": "SME Spotlight",
        "author_name": "Grace Muthoni",
        "author_role": "Business Analyst",
        "published_at": datetime(2023, 11, 8, 9, 0, tzinfo=timezone.utc),
        "excerpt": (
            "Spreadsheets are useful until they become the bottleneck. These five signs show "
            "when an SME should move to a database, CRM, or lightweight business system."
        ),
        "body": (
            "Every Kenyan business starts with spreadsheets. They are free, flexible, and everyone "
            "already knows how to use them. The problem is that spreadsheets do not scale - and "
            "the signs of outgrowing them often appear long before business owners acknowledge them.\n\n"
            "## 1. More than two people edit the same file\n\n"
            "The moment a second person opens your inventory sheet and saves their changes over "
            "yours, you have a data integrity problem. Multiply this by a team of five or ten and "
            "the spreadsheet has become a liability, not an asset.\n\n"
            "## 2. You email reports instead of generating them\n\n"
            "If someone in your business spends time each week manually compiling data from "
            "multiple sheets to send a summary, you are paying salary for a job a database and a "
            "simple dashboard could do in seconds.\n\n"
            "## 3. Your sales process lives in someone's head\n\n"
            "When the person who manages your WhatsApp inquiries goes on leave and new leads "
            "simply wait unanswered, you do not have a process - you have a dependency. A simple "
            "CRM, even a lightweight custom one, solves this.\n\n"
            "## 4. You cannot answer basic questions instantly\n\n"
            "\"How many units of product X did we sell last month?\" should not require anyone to "
            "look anything up. If it does, your data is trapped in a format that cannot serve you.\n\n"
            "## 5. Reconciliation takes a full day\n\n"
            "Month-end reconciliation that takes more than an hour is a signal. That time should "
            "be spent analysing the numbers, not assembling them."
        ),
    },
    {
        "title": "What \"Vetted Developer\" Actually Means - And Why It Matters",
        "slug": "what-vetted-developer-actually-means",
        "category": "Marketplace",
        "author_name": "Kevin Kariuki",
        "author_role": "Platform Lead",
        "published_at": datetime(2023, 9, 3, 9, 0, tzinfo=timezone.utc),
        "excerpt": (
            "Vetting should mean more than a profile badge. SoftMarket Kenya looks for technical "
            "evidence, references, communication habits, and post-project accountability."
        ),
        "body": (
            "The word \"vetted\" has been used so liberally in the gig economy that it has nearly "
            "lost its meaning. We want to be specific about what it means on SoftMarket Kenya, "
            "because the businesses that use this platform are making real financial commitments "
            "based on it.\n\n"
            "## Technical review\n\n"
            "Every developer on the platform has submitted work samples or completed a technical "
            "assessment. We are not looking for perfection - we are looking for genuine competence "
            "and, critically, evidence that a developer can explain what they have built and why "
            "they made the choices they did.\n\n"
            "## Track record verification\n\n"
            "Where possible we speak to previous clients. This is time-consuming but it is the "
            "single most reliable signal we have found. A developer with two strong references "
            "from satisfied Kenyan clients tells you more than any certification.\n\n"
            "## Communication standards\n\n"
            "Technical skill without communication is a project risk. We evaluate how developers "
            "respond to briefs, ask clarifying questions, and handle scope changes. Many failed "
            "software projects in Kenya are not technical failures - they are communication "
            "failures that compounded over time.\n\n"
            "Vetting is not a one-time event. Developers are reviewed after each project, and the "
            "rating system is designed so that one exceptional score cannot paper over a pattern "
            "of problems."
        ),
    },
    {
        "title": "AI-Assisted Development Is Coming to Kenyan Software Projects - Here Is the Honest Assessment",
        "slug": "ai-assisted-development-kenyan-software-projects-honest-assessment",
        "category": "AI & Automation",
        "author_name": "David Njoroge",
        "author_role": "Senior Developer",
        "published_at": datetime(2024, 7, 17, 9, 0, tzinfo=timezone.utc),
        "excerpt": (
            "AI coding tools can compress timelines, but they do not replace local product judgment, "
            "integration expertise, or developer accountability."
        ),
        "body": (
            "The arrival of AI coding assistants - GitHub Copilot, Cursor, Claude - has generated "
            "more confusion than clarity among Kenyan business owners trying to understand what "
            "they mean for project timelines and costs. Let us be direct about what these tools "
            "do and do not change.\n\n"
            "## What has genuinely improved\n\n"
            "Boilerplate code - the repetitive scaffolding that used to take days - is now "
            "generated in minutes. A developer building your CRUD endpoints or authentication "
            "layer is no longer spending their most expensive hours on the least interesting "
            "work. That time shifts toward architecture decisions and business logic, which is "
            "where your money should be going anyway.\n\n"
            "## What has not changed\n\n"
            "AI tools write plausible-looking code. Plausible is not the same as correct, and it "
            "is certainly not the same as appropriate for your specific business context. M-Pesa "
            "webhook handling, NTSA integration, KRA PIN validation - these are local requirements "
            "that no AI model was trained on sufficiently. A developer who uses AI to scaffold a "
            "project still needs deep judgment about what the AI got wrong.\n\n"
            "## The net effect for buyers\n\n"
            "Used well, AI tools compress timelines by 20-35% on well-scoped projects. They do "
            "not eliminate the need for an experienced developer - they amplify one. A poor "
            "developer with AI assistance produces poor code faster. A strong developer with the "
            "same tools delivers more value in less time. The quality of the developer still "
            "matters most."
        ),
    },
]


def seed_blog_posts(apps, schema_editor):
    BlogPost = apps.get_model("marketplace", "BlogPost")
    for post in BLOG_POSTS:
        BlogPost.objects.update_or_create(
            slug=post["slug"],
            defaults={
                **post,
                "status": "published",
            },
        )


def remove_seeded_blog_posts(apps, schema_editor):
    BlogPost = apps.get_model("marketplace", "BlogPost")
    BlogPost.objects.filter(slug__in=[post["slug"] for post in BLOG_POSTS]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("marketplace", "0003_blogpost"),
    ]

    operations = [
        migrations.AddField(
            model_name="blogpost",
            name="author_name",
            field=models.CharField(blank=True, default="", max_length=120),
        ),
        migrations.AddField(
            model_name="blogpost",
            name="author_role",
            field=models.CharField(blank=True, default="", max_length=160),
        ),
        migrations.AddField(
            model_name="blogpost",
            name="category",
            field=models.CharField(blank=True, default="", max_length=80),
        ),
        migrations.RunPython(seed_blog_posts, remove_seeded_blog_posts),
    ]
