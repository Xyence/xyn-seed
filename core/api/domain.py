"""Domain API endpoints - Sites and Customers"""
from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from pydantic import BaseModel
import uuid

from core.database import get_db

router = APIRouter()


# Schemas
class SiteCreate(BaseModel):
    """Request to create a site."""
    name: str
    customer_id: str
    url: Optional[str] = None
    status: str = "active"


class SiteResponse(BaseModel):
    """Site response model."""
    id: str
    customer_id: str
    name: str
    url: Optional[str]
    status: str
    created_at: datetime
    updated_at: datetime


class CustomerCreate(BaseModel):
    """Request to create a customer."""
    name: str
    email: str
    status: str = "active"


class CustomerResponse(BaseModel):
    """Customer response model."""
    id: str
    name: str
    email: str
    status: str
    created_at: datetime
    updated_at: datetime


# Sites endpoints
@router.get("/sites", response_model=List[SiteResponse])
async def list_sites(db: Session = Depends(get_db)):
    """List all sites from pack_core_domain schema.

    Returns:
        List of sites
    """
    result = db.execute(text("""
        SELECT
            id, customer_id, name, url, status, created_at, updated_at
        FROM pack_core_domain.sites
        ORDER BY created_at DESC
    """))

    sites = []
    for row in result:
        sites.append(SiteResponse(
            id=str(row[0]),
            customer_id=str(row[1]),
            name=row[2],
            url=row[3],
            status=row[4],
            created_at=row[5],
            updated_at=row[6]
        ))

    return sites


@router.post("/sites", response_model=SiteResponse)
async def create_site(site: SiteCreate, db: Session = Depends(get_db)):
    """Create a new site in pack_core_domain schema.

    Args:
        site: Site creation data

    Returns:
        Created site
    """
    # Verify customer exists
    customer_check = db.execute(text("""
        SELECT id FROM pack_core_domain.customers WHERE id = :customer_id
    """), {"customer_id": site.customer_id})

    if not customer_check.fetchone():
        raise HTTPException(status_code=404, detail=f"Customer '{site.customer_id}' not found")

    site_id = str(uuid.uuid4())
    now = datetime.utcnow()

    db.execute(text("""
        INSERT INTO pack_core_domain.sites (id, customer_id, name, url, status, created_at, updated_at)
        VALUES (:id, :customer_id, :name, :url, :status, :created_at, :updated_at)
    """), {
        "id": site_id,
        "customer_id": site.customer_id,
        "name": site.name,
        "url": site.url,
        "status": site.status,
        "created_at": now,
        "updated_at": now
    })
    db.commit()

    return SiteResponse(
        id=site_id,
        customer_id=site.customer_id,
        name=site.name,
        url=site.url,
        status=site.status,
        created_at=now,
        updated_at=now
    )


# Customers endpoints
@router.get("/customers", response_model=List[CustomerResponse])
async def list_customers(db: Session = Depends(get_db)):
    """List all customers from pack_core_domain schema.

    Returns:
        List of customers
    """
    result = db.execute(text("""
        SELECT
            id, name, email, status, created_at, updated_at
        FROM pack_core_domain.customers
        ORDER BY created_at DESC
    """))

    customers = []
    for row in result:
        customers.append(CustomerResponse(
            id=str(row[0]),
            name=row[1],
            email=row[2],
            status=row[3],
            created_at=row[4],
            updated_at=row[5]
        ))

    return customers


@router.post("/customers", response_model=CustomerResponse)
async def create_customer(customer: CustomerCreate, db: Session = Depends(get_db)):
    """Create a new customer in pack_core_domain schema.

    Args:
        customer: Customer creation data

    Returns:
        Created customer
    """
    # Check if email already exists
    email_check = db.execute(text("""
        SELECT id FROM pack_core_domain.customers WHERE email = :email
    """), {"email": customer.email})

    if email_check.fetchone():
        raise HTTPException(status_code=400, detail=f"Customer with email '{customer.email}' already exists")

    customer_id = str(uuid.uuid4())
    now = datetime.utcnow()

    db.execute(text("""
        INSERT INTO pack_core_domain.customers (id, name, email, status, created_at, updated_at)
        VALUES (:id, :name, :email, :status, :created_at, :updated_at)
    """), {
        "id": customer_id,
        "name": customer.name,
        "email": customer.email,
        "status": customer.status,
        "created_at": now,
        "updated_at": now
    })
    db.commit()

    return CustomerResponse(
        id=customer_id,
        name=customer.name,
        email=customer.email,
        status=customer.status,
        created_at=now,
        updated_at=now
    )
