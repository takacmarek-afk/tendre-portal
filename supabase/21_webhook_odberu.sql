-- =============================================================================
--  SLACK/TEAMS WEBHOOK PRI ODBERE
--  Vloz do Supabase: SQL Editor -> New query -> Run. Spustit sa da opakovane.
--  Spustaj PO 20_frekvencia_odberu.sql.
-- =============================================================================
--
--  CO TO JE
--  Odberateľ si popri e-maile môže voliteľne pridať Slack/Teams incoming
--  webhook URL. `posli_email.py` naň pri každom digeste pošle rovnaký obsah
--  ako do e-mailu (posli_webhook, format podla domeny — hooks.slack.com vs
--  Teams MessageCard). Ide o ich vlastnu URL pre ich vlastny kanal, rovnaky
--  typ udaja ako e-mailova adresa — nic sa tym nezdiela s nikym dalsim.
-- =============================================================================

alter table public.odber add column if not exists webhook_url text;

select 'odber: pridany webhook_url (Slack/Teams).' as vysledok;
