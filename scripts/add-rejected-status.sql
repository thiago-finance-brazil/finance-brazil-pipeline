-- ============================================================
-- FINANCE BRAZIL — Migration preventiva
-- ============================================================
-- Garante que `articles.status` aceita 'rejected' (usado pela
-- decisão "reject" do orchestrator de validação no Dia 4+).
--
-- Necessário ANTES do Dia 5 (orchestrator main.py que efetiva
-- INSERT na tabela articles). Se sua constraint atual já permite
-- 'rejected', o ALTER é no-op e seguro.
-- ============================================================

-- Passo 1 — Verificar a constraint atual:
-- (Rode primeiro essa query no SQL Editor pra ver os valores aceitos)
SELECT pg_get_constraintdef(c.oid) AS constraint_def
FROM pg_constraint c
JOIN pg_class t ON c.conrelid = t.oid
WHERE t.relname = 'articles'
  AND c.contype = 'c'
  AND c.conname LIKE '%status%';

-- ============================================================
-- Passo 2 — Drop + recria com 'rejected' incluído.
-- ============================================================
-- ATENÇÃO: ajuste a lista IN(...) abaixo conforme a constraint
-- mostrada no Passo 1. Se já houver 'queue', 'archived', etc,
-- inclua todos os status existentes na sua base.

ALTER TABLE articles
  DROP CONSTRAINT IF EXISTS articles_status_check;

ALTER TABLE articles
  ADD CONSTRAINT articles_status_check
  CHECK (status IN ('pending', 'published', 'rejected', 'queue', 'archived'));

-- ============================================================
-- Passo 3 — Confirmar:
-- ============================================================
-- SELECT pg_get_constraintdef(c.oid) AS constraint_def
-- FROM pg_constraint c
-- JOIN pg_class t ON c.conrelid = t.oid
-- WHERE t.relname = 'articles' AND c.conname = 'articles_status_check';
