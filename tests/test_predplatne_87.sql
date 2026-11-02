-- Test migracie 87 (automaticke obnovovanie cez Stripe). Lokalna DB so schemou
-- a migraciami. Kazdy riadok vypisu ma tvar "nazov | ok" (ok = t).
\set ON_ERROR_STOP on
\pset format unaligned
\pset tuples_only on
insert into public.organizations(id,nazov) values ('aaaaaaaa-0000-0000-0000-000000000087','Predplatna s.r.o.');
insert into public.subscriptions(org_id,plan,stav,trial_konci,obdobie_konci)
  values ('aaaaaaaa-0000-0000-0000-000000000087','trial','trial', now()+interval '3 days', null);
insert into public.platby(reference,org_id,plan,obdobie,suma,stav)
  values ('11111111-0000-0000-0000-000000000087','aaaaaaaa-0000-0000-0000-000000000087','growth','rok',890,'vytvorena');

select 'prva platba aktivuje', (public.spracuj_platbu_stripe('11111111-0000-0000-0000-000000000087','zaplatena','checkout.session.completed')->>'kod') = 'AKTIVOVANE';
select 'prepojenie', (public.prepoj_predplatne_stripe('11111111-0000-0000-0000-000000000087','sub_1','cus_1','in_1')->>'kod') = 'PREPOJENE';
select 'auto_obnova a id', auto_obnova and stripe_subscription_id='sub_1' and stripe_customer_id='cus_1' from public.subscriptions where org_id='aaaaaaaa-0000-0000-0000-000000000087';
select 'prva faktura nepridava riadok', (public.obnov_predplatne_stripe('sub_1','in_1',890,now()+interval '1 year')->>'kod') = 'UZ_SPRACOVANE';
select 'obnova', (public.obnov_predplatne_stripe('sub_1','in_2',890,now()+interval '2 years')->>'kod') = 'OBNOVENE';
select 'obnova idempotentna', (public.obnov_predplatne_stripe('sub_1','in_2',890,now()+interval '2 years')->>'kod') = 'UZ_SPRACOVANE';
select 'dva zaplatene riadky', count(*) = 2 from public.platby where org_id='aaaaaaaa-0000-0000-0000-000000000087' and stav='zaplatena';
select 'obnova ma plan a obdobie', plan='growth' and obdobie='rok' and suma=890 from public.platby where stripe_invoice_id='in_2';
select 'obdobie predlzene', obdobie_konci > now()+interval '23 months' and stav='aktivne' from public.subscriptions where org_id='aaaaaaaa-0000-0000-0000-000000000087';
select 'obnova s kratsim datumom', (public.obnov_predplatne_stripe('sub_1','in_3',890,now()+interval '1 day')->>'ok')::boolean;
select 'obdobie sa neskracuje', obdobie_konci > now()+interval '23 months' from public.subscriptions where org_id='aaaaaaaa-0000-0000-0000-000000000087';
select 'nezname predplatne bez chyby', (public.obnov_predplatne_stripe('sub_x','in_9',10,null)->>'kod') = 'NEZNAME_PREDPLATNE';
select 'zrusenie obnovy', (public.nastav_obnovu_stripe('sub_1', false)->>'kod') = 'ZRUSENE';
select 'obnova vypnuta', not auto_obnova from public.subscriptions where org_id='aaaaaaaa-0000-0000-0000-000000000087';
select 'anon nesmie', not has_function_privilege('anon','public.obnov_predplatne_stripe(text,text,numeric,timestamptz)','execute');
select 'authenticated nesmie', not has_function_privilege('authenticated','public.prepoj_predplatne_stripe(uuid,text,text,text)','execute');
