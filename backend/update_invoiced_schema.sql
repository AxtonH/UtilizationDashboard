-- Update monthly_invoiced_totals table to support new calculation formula
-- Formula: amount_aed = invoices_total - credit_notes_total + reversed_total

-- Add new columns for component breakdown
ALTER TABLE monthly_invoiced_totals
ADD COLUMN IF NOT EXISTS invoices_total NUMERIC(20, 2) DEFAULT 0,
ADD COLUMN IF NOT EXISTS credit_notes_total NUMERIC(20, 2) DEFAULT 0,
ADD COLUMN IF NOT EXISTS reversed_total NUMERIC(20, 2) DEFAULT 0;

-- Update existing rows: set component values to current amount_aed (invoices_total)
-- This assumes existing data was invoices only (no credit notes or reversed)
-- You may want to recalculate these by running the updated code
UPDATE monthly_invoiced_totals
SET 
    invoices_total = COALESCE(amount_aed, 0),
    credit_notes_total = 0,
    reversed_total = 0
WHERE invoices_total IS NULL OR invoices_total = 0;

-- Add comment to document the formula
COMMENT ON COLUMN monthly_invoiced_totals.amount_aed IS 'Total calculated as: invoices_total - credit_notes_total + reversed_total';
COMMENT ON COLUMN monthly_invoiced_totals.invoices_total IS 'Total AED from invoices (out_invoice, not reversed, partner_id != 10)';
COMMENT ON COLUMN monthly_invoiced_totals.credit_notes_total IS 'Total AED from credit notes (out_refund, not reversed, partner_id != 10) - will be subtracted';
COMMENT ON COLUMN monthly_invoiced_totals.reversed_total IS 'Total AED from reversed invoices (out_invoice, payment_state=reversed, partner_id != 10) - will be added';

-- Notify PostgREST to reload schema cache
NOTIFY pgrst, 'reload schema';

