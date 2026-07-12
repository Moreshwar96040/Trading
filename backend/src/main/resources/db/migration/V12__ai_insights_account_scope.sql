-- V12: allow account-level AI insights (symbol_id = 0 sentinel for e.g. the
-- REVIEW/leaks narrative, which belongs to the whole account, not one symbol).
ALTER TABLE ai_insights DROP CONSTRAINT IF EXISTS ai_insights_symbol_id_fkey;
