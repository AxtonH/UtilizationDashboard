# Monthly Invoiced Totals Schema Explanation

## Table: `monthly_invoiced_totals`

This table stores **cached monthly invoiced amounts** to improve dashboard performance. Instead of querying Odoo every time, we cache the calculated totals.

---

## Schema Structure

```sql
CREATE TABLE monthly_invoiced_totals (
    year INTEGER NOT NULL,                    -- Year (e.g., 2025)
    month INTEGER NOT NULL,                    -- Month (1-12)
    amount_aed NUMERIC(20, 2) NOT NULL,       -- Final calculated total (what shows in dashboard)
    invoices_total NUMERIC(20, 2) DEFAULT 0,  -- Component: Total from invoices
    credit_notes_total NUMERIC(20, 2) DEFAULT 0, -- Component: Total from credit notes
    reversed_total NUMERIC(20, 2) DEFAULT 0,  -- Component: Total from reversed invoices
    updated_at TIMESTAMP WITH TIME ZONE,      -- When this record was last updated
    PRIMARY KEY (year, month)
);
```

---

## What Each Column Stores

### 1. **`year`** and **`month`**
   - **Purpose**: Identifies which month this data represents
   - **Example**: `year = 2025`, `month = 10` means October 2025

### 2. **`amount_aed`** (Final Total)
   - **Purpose**: The final calculated amount that appears in the dashboard
   - **Formula**: `amount_aed = invoices_total - credit_notes_total + reversed_total`
   - **Example**: `150000.00` AED

### 3. **`invoices_total`** (Component 1)
   - **Purpose**: Sum of all regular customer invoices
   - **What it includes**:
     - `move_type = "out_invoice"` (Customer Invoice)
     - `payment_state != "reversed"` (Not reversed)
     - `partner_id != 10` (Excluding internal company)
     - `invoice_date` within the month
   - **Example**: `200000.00` AED
   - **Meaning**: Total value of all invoices issued this month

### 4. **`credit_notes_total`** (Component 2)
   - **Purpose**: Sum of all credit notes (refunds/returns)
   - **What it includes**:
     - `move_type = "out_refund"` (Customer Credit Note)
     - `payment_state != "reversed"` (Not reversed)
     - `partner_id != 10` (Excluding internal company)
     - `invoice_date` within the month
   - **Example**: `30000.00` AED
   - **Meaning**: Total value of credit notes issued this month (will be subtracted)

### 5. **`reversed_total`** (Component 3)
   - **Purpose**: Sum of all reversed invoices
   - **What it includes**:
     - `move_type = "out_invoice"` (Customer Invoice)
     - `payment_state = "reversed"` (Reversed invoices)
     - `partner_id != 10` (Excluding internal company)
     - `invoice_date` within the month
   - **Example**: `20000.00` AED
   - **Meaning**: Total value of invoices that were reversed this month (will be added back)

### 6. **`updated_at`**
   - **Purpose**: Timestamp of when this record was last updated
   - **Example**: `2025-10-15 14:30:00+00`

---

## Example Data Row

Here's what a complete row might look like:

| year | month | amount_aed | invoices_total | credit_notes_total | reversed_total | updated_at |
|------|-------|------------|----------------|-------------------|----------------|------------|
| 2025 | 10    | 190000.00  | 200000.00      | 30000.00          | 20000.00       | 2025-10-15 14:30:00+00 |

**Calculation breakdown:**
```
amount_aed = invoices_total - credit_notes_total + reversed_total
190000.00 = 200000.00 - 30000.00 + 20000.00
```

**What this means:**
- In October 2025, you issued invoices worth **200,000 AED**
- You issued credit notes worth **30,000 AED** (refunds/returns)
- You reversed invoices worth **20,000 AED** (added back)
- **Net invoiced amount: 190,000 AED**

---

## Real-World Scenario Example

### Scenario: October 2025

**Invoices issued:**
- Invoice #001: 50,000 AED
- Invoice #002: 75,000 AED
- Invoice #003: 75,000 AED
- **Total invoices: 200,000 AED**

**Credit notes issued:**
- Credit Note #001: 20,000 AED (refund for Invoice #001)
- Credit Note #002: 10,000 AED (partial refund)
- **Total credit notes: 30,000 AED**

**Reversed invoices:**
- Invoice #004: 20,000 AED (was reversed)
- **Total reversed: 20,000 AED**

**Final calculation:**
```
amount_aed = 200,000 - 30,000 + 20,000 = 190,000 AED
```

**Stored in database:**
```json
{
  "year": 2025,
  "month": 10,
  "amount_aed": 190000.00,
  "invoices_total": 200000.00,
  "credit_notes_total": 30000.00,
  "reversed_total": 20000.00,
  "updated_at": "2025-10-15T14:30:00Z"
}
```

---

## Why Store Components Separately?

1. **Transparency**: You can see exactly what contributed to the total
2. **Debugging**: Easier to identify discrepancies
3. **Reporting**: Can generate reports showing invoices vs credit notes vs reversed
4. **Audit Trail**: Historical breakdown of what happened each month

---

## How It's Used

1. **Dashboard loads**: Checks cache first (fast)
2. **If cached**: Uses `amount_aed` directly
3. **If not cached**: 
   - Fetches from Odoo
   - Calculates all three components
   - Stores breakdown in database
   - Returns `amount_aed` to dashboard

---

## Notes

- **One row per month**: Each year-month combination has exactly one row
- **Current month**: Always recalculated fresh from Odoo (not cached)
- **Past months**: Cached for performance
- **Backward compatible**: Old code still works (components are optional)













