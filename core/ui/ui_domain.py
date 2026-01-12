"""UI routes for domain console (sites and customers)"""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import text

from core.database import get_db

router = APIRouter()
templates = Jinja2Templates(directory="core/templates")


@router.get("/domain", response_class=HTMLResponse)
async def domain_page(
    request: Request,
    db: Session = Depends(get_db)
):
    """Domain console page showing sites and customers."""
    # Fetch customers
    customers_result = db.execute(text("""
        SELECT id, name, email, status, created_at, updated_at
        FROM pack_core_domain.customers
        ORDER BY created_at DESC
    """))
    customers = [
        {
            "id": str(row[0]),
            "name": row[1],
            "email": row[2],
            "status": row[3],
            "created_at": row[4],
            "updated_at": row[5]
        }
        for row in customers_result
    ]

    # Fetch sites
    sites_result = db.execute(text("""
        SELECT s.id, s.customer_id, s.name, s.url, s.status, s.created_at, s.updated_at,
               c.name as customer_name
        FROM pack_core_domain.sites s
        LEFT JOIN pack_core_domain.customers c ON s.customer_id = c.id
        ORDER BY s.created_at DESC
    """))
    sites = [
        {
            "id": str(row[0]),
            "customer_id": str(row[1]),
            "name": row[2],
            "url": row[3],
            "status": row[4],
            "created_at": row[5],
            "updated_at": row[6],
            "customer_name": row[7]
        }
        for row in sites_result
    ]

    return templates.TemplateResponse(
        "domain.html",
        {
            "request": request,
            "customers": customers,
            "sites": sites
        }
    )
