-- 0006 · The read-only inspection role must not read document content.
--
-- Extracted page text (docs.text_index.body) and extracted entity values (docs.entities.value)
-- are document content — they can include a victim's name. Auditors and anyone inspecting the
-- database through cfv_readonly see the structure and the metadata, never the words.

REVOKE SELECT ON docs.text_index FROM cfv_readonly;
GRANT SELECT (id, version_id, document_id, page_no, redacted) ON docs.text_index TO cfv_readonly;

REVOKE SELECT ON docs.entities FROM cfv_readonly;
GRANT SELECT (id, version_id, type, page_no, is_pii, is_victim_identifier, confidence, source)
  ON docs.entities TO cfv_readonly;

COMMENT ON COLUMN docs.text_index.body IS 'Page text for full-text search. Readable by the app only; cfv_readonly is not granted this column.';
COMMENT ON COLUMN docs.entities.value IS 'Extracted value (may be personal data). Not granted to cfv_readonly.';
