from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .forms import DeveloperApplicationForm, ProjectRequestForm
from .models import BlogPost, Payment, ProjectRequest
from .services import (
    MpesaClient,
    analytics_summary,
    assign_best_developers,
    create_deposit_payment,
    generate_quote,
    handle_mpesa_callback,
    notify_admins_for_developer,
    notify_admins_for_project,
    parsed_json_body,
    project_requests_csv,
    project_requests_xlsx,
    seed_default_services,
)


def home(request):
    seed_default_services()
    if request.method == "POST":
        form_name = request.POST.get("form-name")
        if form_name == "project-brief":
            form = ProjectRequestForm(request.POST)
            if form.is_valid():
                project = form.save()
                generate_quote(project)
                assign_best_developers(project)
                notify_admins_for_project(project)
                messages.success(request, "Project brief saved. We will review it and follow up.")
            else:
                messages.error(request, "Please check the project brief fields and try again.")
        elif form_name == "developer-application":
            form = DeveloperApplicationForm(request.POST)
            if form.is_valid():
                application = form.save()
                notify_admins_for_developer(application)
                messages.success(request, "Developer application saved. We will review your portfolio.")
            else:
                messages.error(request, "Please check the developer application fields and try again.")
        else:
            messages.error(request, "Unknown form submission.")

    return render(request, "marketplace/home.html")


def work(request):
    return render(request, "marketplace/work.html")


def about(request):
    return render(request, "marketplace/about.html")


def process(request):
    return render(request, "marketplace/process.html")


def blog_list(request):
    posts = BlogPost.objects.filter(
        status=BlogPost.Status.PUBLISHED,
        published_at__isnull=False,
    )
    return render(request, "marketplace/blog_list.html", {"posts": posts})


def blog_detail(request, slug):
    post = get_object_or_404(
        BlogPost,
        slug=slug,
        status=BlogPost.Status.PUBLISHED,
        published_at__isnull=False,
    )
    return render(request, "marketplace/blog_detail.html", {"post": post})


@staff_member_required
def analytics_dashboard(request):
    return render(request, "marketplace/analytics.html", {"summary": analytics_summary()})


@staff_member_required
def export_project_requests(request):
    response = HttpResponse(project_requests_csv(), content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="softmarket-project-requests.csv"'
    return response


@staff_member_required
def export_project_requests_xlsx(request):
    response = HttpResponse(
        project_requests_xlsx(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = 'attachment; filename="softmarket-project-requests.xlsx"'
    return response


@staff_member_required
@require_POST
def initiate_mpesa_deposit(request, project_id):
    project = get_object_or_404(ProjectRequest, pk=project_id)
    if not project.deposit_amount:
        generate_quote(project)
    payment = create_deposit_payment(project)
    result = MpesaClient().initiate_stk_push(payment)
    return JsonResponse({"payment_id": payment.id, "result": result})


@csrf_exempt
@require_POST
def mpesa_callback(request):
    payload = parsed_json_body(request)
    payment = handle_mpesa_callback(payload)
    return JsonResponse({"ok": True, "payment_id": payment.id if payment else None})


@staff_member_required
def payment_status(request, payment_id):
    payment = get_object_or_404(Payment, pk=payment_id)
    return JsonResponse(
        {
            "id": payment.id,
            "project_id": payment.project_id,
            "amount": payment.amount,
            "status": payment.status,
            "mpesa_receipt": payment.mpesa_receipt,
            "result_description": payment.result_description,
        }
    )
