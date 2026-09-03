/**
 * SoftMarket Kenya — Domain Errors & Error Boundaries
 */

export abstract class DomainError extends Error {
  abstract readonly code: string;
  readonly details?: Record<string, unknown>;

  constructor(message: string, details?: Record<string, unknown>) {
    super(message);
    this.name = this.constructor.name;
    this.details = details;
    Object.setPrototypeOf(this, new.target.prototype);
  }

  toJSON() {
    return {
      error: this.name,
      code: this.code,
      message: this.message,
      details: this.details,
    };
  }
}

export class MpesaValidationError extends DomainError {
  readonly code = "MPESA_VALIDATION_FAILED";
}

export class MpesaAuthenticationError extends DomainError {
  readonly code = "MPESA_AUTH_FAILED";
}

export class MpesaIdempotencyError extends DomainError {
  readonly code = "MPESA_IDEMPOTENCY_CONFLICT";
}

export class InventoryShortfallError extends DomainError {
  readonly code = "INVENTORY_SHORTFALL";
}

export class InventoryReservationExpiredError extends DomainError {
  readonly code = "INVENTORY_RESERVATION_EXPIRED";
}

export class InvalidStateTransitionError extends DomainError {
  readonly code = "INVALID_STATE_TRANSITION";
}

export class DeliveryZoneNotFoundError extends DomainError {
  readonly code = "DELIVERY_ZONE_NOT_FOUND";
}

export class CouponValidationError extends DomainError {
  readonly code = "COUPON_INVALID";
}

export class CurrencyCalculationError extends DomainError {
  readonly code = "CURRENCY_CALCULATION_ERROR";
}
