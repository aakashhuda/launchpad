from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from src.core.database import get_db
from src.core.dependencies import get_optional_current_user, require_verified_role
from src.products.schemas import (
    LaunchScheduleRequest,
    ProductCreate,
    ProductDetailRead,
    ProductRead,
    ProductUpdate,
    SubmissionRead,
)
from src.products.service import ProductLaunchService, ProductService, SubmissionService
from src.users.models import User

router = APIRouter()


@router.post("", response_model=ProductDetailRead, status_code=status.HTTP_201_CREATED)
def create_product(
    payload: ProductCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_verified_role("founder")),
) -> ProductDetailRead:
    return ProductService(db).create_draft(current_user, payload)


@router.get("/mine", response_model=list[ProductRead])
def list_my_products(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_verified_role("founder")),
) -> list[ProductRead]:
    return ProductService(db).list_for_user(current_user)


@router.get("/{product_id}", response_model=ProductDetailRead)
def read_product(
    product_id: int,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
) -> ProductDetailRead:
    return ProductService(db).get_readable(current_user, product_id)


@router.patch("/{product_id}", response_model=ProductDetailRead)
def update_product(
    product_id: int,
    payload: ProductUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_verified_role("founder")),
) -> ProductDetailRead:
    return ProductService(db).update(current_user, product_id, payload)


@router.post("/{product_id}/submit", response_model=SubmissionRead)
def submit_product(
    product_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_verified_role("founder")),
) -> SubmissionRead:
    return SubmissionService(db).submit_for_review(current_user, product_id)


@router.post("/{product_id}/launch", response_model=ProductDetailRead)
def schedule_launch(
    product_id: int,
    payload: LaunchScheduleRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_verified_role("founder")),
) -> ProductDetailRead:
    return ProductLaunchService(db).schedule(current_user, product_id, payload)
