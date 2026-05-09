# COMPLETE LEADBOOK PROJECT AUDIT

## DATABASE AUDIT (Production)

### SQL QUERY 1 - Todas las tablas
```sql
SELECT schemaname, tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename;
```
```text
schemaname | tablename                       
-----------+---------------------------------
public     | api_adminalert                  
public     | api_agent                       
public     | api_agent_groups                
public     | api_agent_user_permissions      
public     | api_amenidadpreset              
public     | api_apibundle                   
public     | api_apibundleassignment         
public     | api_apikey                      
public     | api_apirequestlog               
public     | api_bannedemail                 
public     | api_bannedip                    
public     | api_bundleapiextra              
public     | api_configuracionsistema        
public     | api_generatedasset              
public     | api_listado                     
public     | api_notificacion                
public     | api_otpcode                     
public     | api_plan                        
public     | api_politicaprivacidad          
public     | api_property                    
public     | api_propertyimage               
public     | api_suscripcion                 
public     | api_terminoscondiciones         
public     | api_usagelog                    
public     | api_userapiquota                
public     | api_userbanrecord               
public     | api_videomusic                  
public     | api_videosfx                    
public     | auth_group                      
public     | auth_group_permissions          
public     | auth_permission                 
public     | django_admin_log                
public     | django_content_type             
public     | django_migrations               
public     | django_session                  
public     | token_blacklist_blacklistedtoken
public     | token_blacklist_outstandingtoken
```

### SQL QUERY 2 - Estructura completa de todas las tablas
```sql
SELECT table_name, column_name, data_type, is_nullable, column_default FROM information_schema.columns WHERE table_schema = 'public' AND table_name LIKE 'api_%' ORDER BY table_name, ordinal_position;
```
```text
table_name                 | column_name               | data_type                | is_nullable | column_default
---------------------------+---------------------------+--------------------------+-------------+---------------
api_adminalert             | id                        | bigint                   | NO          | None          
api_adminalert             | type                      | character varying        | NO          | None          
api_adminalert             | severity                  | character varying        | NO          | None          
api_adminalert             | title                     | character varying        | NO          | None          
api_adminalert             | message                   | text                     | NO          | None          
api_adminalert             | is_read                   | boolean                  | NO          | None          
api_adminalert             | created_at                | timestamp with time zone | NO          | None          
api_adminalert             | related_api_key_id        | bigint                   | YES         | None          
api_adminalert             | related_user_id           | bigint                   | YES         | None          
api_agent                  | id                        | bigint                   | NO          | None          
api_agent                  | password                  | character varying        | NO          | None          
api_agent                  | last_login                | timestamp with time zone | YES         | None          
api_agent                  | is_superuser              | boolean                  | NO          | None          
api_agent                  | email                     | character varying        | NO          | None          
api_agent                  | nombre                    | character varying        | NO          | None          
api_agent                  | telefono                  | character varying        | YES         | None          
api_agent                  | agencia                   | character varying        | YES         | None          
api_agent                  | activo                    | boolean                  | NO          | None          
api_agent                  | fecha_registro            | timestamp with time zone | NO          | None          
api_agent                  | is_active                 | boolean                  | NO          | None          
api_agent                  | is_staff                  | boolean                  | NO          | None          
api_agent                  | agentes_asociados         | jsonb                    | NO          | None          
api_agent                  | logo_url                  | text                     | YES         | None          
api_agent                  | nombre_inmobiliaria       | character varying        | YES         | None          
api_agent                  | plan_nombre               | character varying        | NO          | None          
api_agent                  | nicho                     | character varying        | YES         | None          
api_agent                  | pais                      | character varying        | YES         | None          
api_agent                  | meta_access_token         | text                     | YES         | None          
api_agent                  | meta_instagram_account_id | character varying        | YES         | None          
api_agent                  | mp_customer_id            | character varying        | YES         | None          
api_agent                  | mp_subscription_id        | character varying        | YES         | None          
api_agent                  | plan_activo               | boolean                  | NO          | None          
api_agent                  | plan_seleccionado         | boolean                  | NO          | None          
api_agent                  | plan                      | character varying        | NO          | None          
api_agent                  | eliminado_en              | timestamp with time zone | YES         | None          
api_agent                  | bio                       | text                     | YES         | None          
api_agent                  | nacionalidad              | character varying        | YES         | None          
api_agent                  | sitio_web                 | character varying        | YES         | None          
api_agent                  | last_login_ip             | inet                     | YES         | None          
api_agent                  | last_login_user_agent     | text                     | YES         | None          
api_agent_groups           | id                        | bigint                   | NO          | None          
api_agent_groups           | agent_id                  | bigint                   | NO          | None          
api_agent_groups           | group_id                  | integer                  | NO          | None          
api_agent_user_permissions | id                        | bigint                   | NO          | None          
api_agent_user_permissions | agent_id                  | bigint                   | NO          | None          
api_agent_user_permissions | permission_id             | integer                  | NO          | None          
api_amenidadpreset         | id                        | bigint                   | NO          | None          
api_amenidadpreset         | nombre                    | character varying        | NO          | None          
api_amenidadpreset         | creado                    | timestamp with time zone | NO          | None          
api_amenidadpreset         | agente_id                 | bigint                   | NO          | None          
api_apibundle              | id                        | bigint                   | NO          | None          
api_apibundle              | nombre                    | character varying        | NO          | None          
api_apibundle              | status                    | character varying        | NO          | None          
api_apibundle              | notas                     | text                     | YES         | None          
api_apibundle              | created_at                | timestamp with time zone | NO          | None          
api_apibundle              | updated_at                | timestamp with time zone | NO          | None          
api_apibundle              | key_elevenlabs_id         | bigint                   | YES         | None          
api_apibundle              | key_gemini_id             | bigint                   | YES         | None          
api_apibundle              | key_uploadpost_id         | bigint                   | YES         | None          
api_apibundleassignment    | id                        | bigint                   | NO          | None          
api_apibundleassignment    | asignado_en               | timestamp with time zone | NO          | None          
api_apibundleassignment    | liberado_en               | timestamp with time zone | YES         | None          
api_apibundleassignment    | activo                    | boolean                  | NO          | None          
api_apibundleassignment    | bundle_id                 | bigint                   | NO          | None          
api_apibundleassignment    | usuario_id                | bigint                   | NO          | None          
api_apikey                 | id                        | bigint                   | NO          | None          
api_apikey                 | servicio                  | character varying        | NO          | None          
api_apikey                 | api_key                   | text                     | NO          | None          
api_apikey                 | status                    | character varying        | NO          | None          
api_apikey                 | assigned_at               | timestamp with time zone | YES         | None          
api_apikey                 | daily_limit               | integer                  | NO          | None          
api_apikey                 | monthly_limit             | integer                  | YES         | None          
api_apikey                 | requests_today            | integer                  | NO          | None          
api_apikey                 | requests_this_month       | integer                  | NO          | None          
api_apikey                 | total_requests            | integer                  | NO          | None          
api_apikey                 | last_used_at              | timestamp with time zone | YES         | None          
api_apikey                 | last_health_check         | timestamp with time zone | YES         | None          
api_apikey                 | last_health_status        | boolean                  | NO          | None          
api_apikey                 | error_count               | integer                  | NO          | None          
api_apikey                 | notes                     | text                     | YES         | None          
api_apikey                 | created_at                | timestamp with time zone | NO          | None          
api_apikey                 | updated_at                | timestamp with time zone | NO          | None          
api_apikey                 | assigned_to_id            | bigint                   | YES         | None          
api_apikey                 | empresa                   | character varying        | YES         | None          
api_apikey                 | label                     | character varying        | YES         | None          
api_apikey                 | is_monthly_exhausted      | boolean                  | NO          | None          
api_apirequestlog          | id                        | bigint                   | NO          | None          
api_apirequestlog          | service                   | character varying        | NO          | None          
api_apirequestlog          | endpoint                  | character varying        | NO          | None          
api_apirequestlog          | method                    | character varying        | NO          | None          
api_apirequestlog          | status_code               | integer                  | YES         | None          
api_apirequestlog          | success                   | boolean                  | NO          | None          
api_apirequestlog          | response_time_ms          | integer                  | NO          | None          
api_apirequestlog          | tokens_used               | integer                  | YES         | None          
api_apirequestlog          | characters_used           | integer                  | YES         | None          
api_apirequestlog          | cost_estimate             | numeric                  | YES         | None          
api_apirequestlog          | error_message             | text                     | YES         | None          
api_apirequestlog          | request_context           | jsonb                    | NO          | None          
api_apirequestlog          | created_at                | timestamp with time zone | NO          | None          
api_apirequestlog          | api_key_id                | bigint                   | NO          | None          
api_apirequestlog          | user_id                   | bigint                   | NO          | None          
api_bannedemail            | id                        | bigint                   | NO          | None          
api_bannedemail            | email                     | character varying        | NO          | None          
api_bannedemail            | banned_at                 | timestamp with time zone | NO          | None          
api_bannedemail            | reason                    | text                     | YES         | None          
api_bannedip               | id                        | bigint                   | NO          | None          
api_bannedip               | ip_address                | inet                     | NO          | None          
api_bannedip               | banned_at                 | timestamp with time zone | NO          | None          
api_bannedip               | reason                    | text                     | YES         | None          
api_bundleapiextra         | id                        | bigint                   | NO          | None          
api_bundleapiextra         | servicio                  | character varying        | NO          | None          
api_bundleapiextra         | activa                    | boolean                  | NO          | None          
api_bundleapiextra         | comprada_en               | timestamp with time zone | NO          | None          
api_bundleapiextra         | pago_id                   | character varying        | YES         | None          
api_bundleapiextra         | api_key_id                | bigint                   | YES         | None          
api_bundleapiextra         | usuario_id                | bigint                   | NO          | None          
api_configuracionsistema   | id                        | bigint                   | NO          | None          
api_configuracionsistema   | clave                     | character varying        | NO          | None          
api_configuracionsistema   | valor                     | text                     | YES         | None          
api_configuracionsistema   | datos                     | jsonb                    | NO          | None          
api_configuracionsistema   | actualizado_en            | timestamp with time zone | NO          | None          
api_generatedasset         | id                        | bigint                   | NO          | None          
api_generatedasset         | asset_type                | character varying        | NO          | None          
api_generatedasset         | file                      | character varying        | YES         | None          
api_generatedasset         | status                    | character varying        | NO          | None          
api_generatedasset         | error_message             | text                     | YES         | None          
api_generatedasset         | created_at                | timestamp with time zone | NO          | None          
api_generatedasset         | completed_at              | timestamp with time zone | YES         | None          
api_generatedasset         | property_id               | bigint                   | NO          | None          
api_listado                | id                        | bigint                   | NO          | None          
api_listado                | titulo                    | character varying        | NO          | None          
api_listado                | tipo_propiedad            | character varying        | NO          | None          
api_listado                | ciudad                    | character varying        | NO          | None          
api_listado                | precio                    | character varying        | NO          | None          
api_listado                | datos                     | jsonb                    | NO          | None          
api_listado                | creado_en                 | timestamp with time zone | NO          | None          
api_listado                | videos_creados            | integer                  | NO          | None          
api_listado                | agente_id                 | bigint                   | NO          | None          
api_listado                | video_status              | character varying        | NO          | None          
api_listado                | video_url                 | character varying        | YES         | None          
api_notificacion           | id                        | bigint                   | NO          | None          
api_notificacion           | tipo                      | character varying        | NO          | None          
api_notificacion           | titulo                    | character varying        | NO          | None          
api_notificacion           | mensaje                   | text                     | NO          | None          
api_notificacion           | leida                     | boolean                  | NO          | None          
api_notificacion           | creada_en                 | timestamp with time zone | NO          | None          
api_notificacion           | usuario_id                | bigint                   | NO          | None          
api_otpcode                | id                        | bigint                   | NO          | None          
api_otpcode                | email                     | character varying        | NO          | None          
api_otpcode                | code_hash                 | character varying        | NO          | None          
api_otpcode                | created_at                | timestamp with time zone | NO          | None          
api_otpcode                | expires_at                | timestamp with time zone | NO          | None          
api_otpcode                | attempts                  | integer                  | NO          | None          
api_otpcode                | verified                  | boolean                  | NO          | None          
api_otpcode                | tipo                      | character varying        | NO          | None          
api_plan                   | id                        | bigint                   | NO          | None          
api_plan                   | nombre                    | character varying        | NO          | None          
api_plan                   | precio_usd                | numeric                  | NO          | None          
api_plan                   | properties_per_month      | integer                  | NO          | None          
api_plan                   | ai_generations            | integer                  | NO          | None          
api_plan                   | image_generations         | integer                  | NO          | None          
api_plan                   | video_generations         | integer                  | NO          | None          
api_plan                   | auto_posting              | boolean                  | NO          | None          
api_plan                   | voice_ai                  | boolean                  | NO          | None          
api_plan                   | branding                  | boolean                  | NO          | None          
api_plan                   | priority_support          | boolean                  | NO          | None          
api_plan                   | mp_plan_id                | character varying        | YES         | None          
api_plan                   | mp_price_id_anual         | character varying        | YES         | None          
api_plan                   | mp_price_id_mensual       | character varying        | YES         | None          
api_politicaprivacidad     | id                        | bigint                   | NO          | None          
api_politicaprivacidad     | titulo                    | character varying        | NO          | None          
api_politicaprivacidad     | contenido                 | text                     | NO          | None          
api_politicaprivacidad     | version                   | character varying        | NO          | None          
api_politicaprivacidad     | fecha_actualizacion       | timestamp with time zone | NO          | None          
api_politicaprivacidad     | activo                    | boolean                  | NO          | None          
api_property               | id                        | bigint                   | NO          | None          
api_property               | title                     | character varying        | NO          | None          
api_property               | description               | text                     | NO          | None          
api_property               | price                     | numeric                  | NO          | None          
api_property               | address                   | character varying        | NO          | None          
api_property               | created_at                | timestamp with time zone | NO          | None          
api_property               | updated_at                | timestamp with time zone | NO          | None          
api_propertyimage          | id                        | bigint                   | NO          | None          
api_propertyimage          | image                     | character varying        | NO          | None          
api_propertyimage          | is_main                   | boolean                  | NO          | None          
api_propertyimage          | created_at                | timestamp with time zone | NO          | None          
api_propertyimage          | property_id               | bigint                   | NO          | None          
api_suscripcion            | id                        | bigint                   | NO          | None          
api_suscripcion            | periodo_inicio            | timestamp with time zone | NO          | None          
api_suscripcion            | periodo_fin               | timestamp with time zone | YES         | None          
api_suscripcion            | properties_used           | integer                  | NO          | None          
api_suscripcion            | ai_used                   | integer                  | NO          | None          
api_suscripcion            | images_used               | integer                  | NO          | None          
api_suscripcion            | videos_used               | integer                  | NO          | None          
api_suscripcion            | extra_credits             | integer                  | NO          | None          
api_suscripcion            | activa                    | boolean                  | NO          | None          
api_suscripcion            | agente_id                 | bigint                   | NO          | None          
api_suscripcion            | plan_id                   | bigint                   | YES         | None          
api_suscripcion            | mp_preapproval_id         | character varying        | YES         | None          
api_suscripcion            | mp_status                 | character varying        | NO          | None          
api_suscripcion            | mp_subscription_id        | character varying        | YES         | None          
api_terminoscondiciones    | id                        | bigint                   | NO          | None          
api_terminoscondiciones    | titulo                    | character varying        | NO          | None          
api_terminoscondiciones    | contenido                 | text                     | NO          | None          
api_terminoscondiciones    | version                   | character varying        | NO          | None          
api_terminoscondiciones    | fecha_actualizacion       | timestamp with time zone | NO          | None          
api_terminoscondiciones    | activo                    | boolean                  | NO          | None          
api_usagelog               | id                        | bigint                   | NO          | None          
api_usagelog               | tipo                      | character varying        | NO          | None          
api_usagelog               | fecha                     | timestamp with time zone | NO          | None          
api_usagelog               | agent_id                  | bigint                   | NO          | None          
api_userapiquota           | id                        | bigint                   | NO          | None          
api_userapiquota           | service                   | character varying        | NO          | None          
api_userapiquota           | daily_limit               | integer                  | NO          | None          
api_userapiquota           | monthly_limit             | integer                  | YES         | None          
api_userapiquota           | requests_today            | integer                  | NO          | None          
api_userapiquota           | requests_this_month       | integer                  | NO          | None          
api_userapiquota           | is_blocked                | boolean                  | NO          | None          
api_userapiquota           | blocked_reason            | character varying        | YES         | None          
api_userapiquota           | last_reset_daily          | timestamp with time zone | YES         | None          
api_userapiquota           | last_reset_monthly        | timestamp with time zone | YES         | None          
api_userapiquota           | user_id                   | bigint                   | NO          | None          
api_userbanrecord          | id                        | bigint                   | NO          | None          
api_userbanrecord          | banned_at                 | timestamp with time zone | NO          | None          
api_userbanrecord          | reason                    | text                     | NO          | None          
api_userbanrecord          | is_active                 | boolean                  | NO          | None          
api_userbanrecord          | banned_by_id              | bigint                   | YES         | None          
api_userbanrecord          | user_id                   | bigint                   | NO          | None          
api_videomusic             | id                        | bigint                   | NO          | None          
api_videomusic             | nombre                    | character varying        | NO          | None          
api_videomusic             | archivo                   | character varying        | NO          | None          
api_videomusic             | duracion_segundos         | double precision         | NO          | None          
api_videomusic             | activo                    | boolean                  | NO          | None          
api_videomusic             | creado_en                 | timestamp with time zone | NO          | None          
api_videosfx               | id                        | bigint                   | NO          | None          
api_videosfx               | nombre                    | character varying        | NO          | None          
api_videosfx               | tipo                      | character varying        | NO          | None          
api_videosfx               | archivo                   | character varying        | NO          | None          
api_videosfx               | activo                    | boolean                  | NO          | None          
api_videosfx               | creado_en                 | timestamp with time zone | NO          | None          
```

### SQL QUERY 3 - Todas las relaciones entre tablas
```sql
SELECT tc.table_name, kcu.column_name, ccu.table_name AS foreign_table, ccu.column_name AS foreign_column FROM information_schema.table_constraints tc JOIN information_schema.key_column_usage kcu ON tc.constraint_name = kcu.constraint_name JOIN information_schema.constraint_column_usage ccu ON ccu.constraint_name = tc.constraint_name WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_name LIKE 'api_%' ORDER BY tc.table_name;
```
```text
table_name                 | column_name        | foreign_table   | foreign_column
---------------------------+--------------------+-----------------+---------------
api_adminalert             | related_user_id    | api_agent       | id            
api_adminalert             | related_api_key_id | api_apikey      | id            
api_agent_groups           | agent_id           | api_agent       | id            
api_agent_groups           | group_id           | auth_group      | id            
api_agent_user_permissions | agent_id           | api_agent       | id            
api_agent_user_permissions | permission_id      | auth_permission | id            
api_amenidadpreset         | agente_id          | api_agent       | id            
api_apibundle              | key_uploadpost_id  | api_apikey      | id            
api_apibundle              | key_gemini_id      | api_apikey      | id            
api_apibundle              | key_elevenlabs_id  | api_apikey      | id            
api_apibundleassignment    | usuario_id         | api_agent       | id            
api_apibundleassignment    | bundle_id          | api_apibundle   | id            
api_apikey                 | assigned_to_id     | api_agent       | id            
api_apirequestlog          | api_key_id         | api_apikey      | id            
api_apirequestlog          | user_id            | api_agent       | id            
api_bundleapiextra         | usuario_id         | api_agent       | id            
api_bundleapiextra         | api_key_id         | api_apikey      | id            
api_generatedasset         | property_id        | api_property    | id            
api_listado                | agente_id          | api_agent       | id            
api_notificacion           | usuario_id         | api_agent       | id            
api_propertyimage          | property_id        | api_property    | id            
api_suscripcion            | agente_id          | api_agent       | id            
api_suscripcion            | plan_id            | api_plan        | id            
api_usagelog               | agent_id           | api_agent       | id            
api_userapiquota           | user_id            | api_agent       | id            
api_userbanrecord          | banned_by_id       | api_agent       | id            
api_userbanrecord          | user_id            | api_agent       | id            
```

### SQL QUERY 4.1 - Datos api_apikey (limit 5)
```sql
SELECT * FROM api_apikey LIMIT 5;
```
```text
id | servicio   | api_key                                                                                                                                                                                                                 | status    | assigned_at | daily_limit | monthly_limit | requests_today | requests_this_month | total_requests | last_used_at | last_health_check | last_health_status | error_count | notes | created_at                       | updated_at                       | assigned_to_id | empresa | label            | is_monthly_exhausted
---+------------+-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+-----------+-------------+-------------+---------------+----------------+---------------------+----------------+--------------+-------------------+--------------------+-------------+-------+----------------------------------+----------------------------------+----------------+---------+------------------+---------------------
46 | uploadpost | eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJlbWFpbCI6Im1hdGlhc2xsYW5vczE0MkBnbWFpbC5jb20iLCJleHAiOjQ5Mjk2MzMwMTcsImp0aSI6IjgyNWU1YzVmLTIyMWMtNDI4ZC05OTJmLTFhNmU3NTFkNTRkNCJ9._bjLsZTdorhVoJpx99-EPTyg0hWP753jr3D4-QhUSK0   | available | None        | 1000        | None          | 0              | 0                   | 0              | None         | None              | True               | 0           | None  | 2026-05-06 14:21:34.199775+00:00 | 2026-05-06 14:21:34.199794+00:00 | None           | None    | API UploadPost 1 | False               
47 | uploadpost | eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJlbWFpbCI6ImFsdmFyZXpvbGl2YTU4MEBnbWFpbC5jb20iLCJleHAiOjQ5MzA5MjIwOTEsImp0aSI6IjI0NzI2OGU1LWRmNDQtNGJlMS1hYmFhLTU0MTMzNjc0Y2NlYSJ9.vExJGiYiPO1LFgk45WCwYMsulSb9Hd0WimEEMUApDBE   | available | None        | 1000        | None          | 0              | 0                   | 0              | None         | None              | True               | 0           | None  | 2026-05-06 14:21:34.199832+00:00 | 2026-05-06 14:21:34.199837+00:00 | None           | None    | API UploadPost 3 | False               
48 | uploadpost | eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJlbWFpbCI6ImVsbWFnbmF0ZWRlaHUxMkBnbWFpbC5jb20iLCJleHAiOjQ5MzA5MjIxMjgsImp0aSI6ImJlNjQwMmJmLTBiYmEtNDEyMy04YzIwLTE1NDVkYWE5OGE1MyJ9.yUVpQjtywvJVkV9X8gw8pBUF_HM3V5oF9TN4JMu_tT4   | available | None        | 1000        | None          | 0              | 0                   | 0              | None         | None              | True               | 0           | None  | 2026-05-06 14:21:34.199871+00:00 | 2026-05-06 14:21:34.199876+00:00 | None           | None    | API UploadPost 4 | False               
49 | uploadpost | eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJlbWFpbCI6ImVsY3Jpc3RpYW5zYXNhNzFAZ21haWwuY29tIiwiZXhwIjo0OTMwOTIyMzEwLCJqdGkiOiIwNDgwMGVkZi0xYTU1LTQ2YmItYWVlMC0yOTcyYmM5ZGMwYzYifQ.3gthLWnImikEyhtagrQew98-zJ4Tn61YN9nthCaZZg4 | available | None        | 1000        | None          | 0              | 0                   | 0              | None         | None              | True               | 0           | None  | 2026-05-06 14:21:34.199908+00:00 | 2026-05-06 14:21:34.199913+00:00 | None           | None    | API UploadPost 5 | False               
50 | uploadpost | eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJlbWFpbCI6ImVsbWFzcm9tZXJvNzFAZ21haWwuY29tIiwiZXhwIjo0OTMwOTIyMzQ0LCJqdGkiOiIxYzdkNmUyNC1mZTFjLTQ2YzItOGRiZC1hZDliMDE0NTQyNTMifQ.kxiHdsSmtx0mJSTSnuAlX5kdc5SyORdCW0k1DWh1MfM     | available | None        | 1000        | None          | 0              | 0                   | 0              | None         | None              | True               | 0           | None  | 2026-05-06 14:21:34.199944+00:00 | 2026-05-06 14:21:34.199949+00:00 | None           | None    | API UploadPost 6 | False               
```

### SQL QUERY 4.2 - Datos api_userapiquota (limit 5)
```sql
SELECT * FROM api_userapiquota LIMIT 5;
```
```text
id | service    | daily_limit | monthly_limit | requests_today | requests_this_month | is_blocked | blocked_reason | last_reset_daily | last_reset_monthly | user_id
---+------------+-------------+---------------+----------------+---------------------+------------+----------------+------------------+--------------------+--------
2  | elevenlabs | 1500        | None          | 0              | 0                   | False      | None           | None             | None               | 6      
3  | uploadpost | 10          | None          | 0              | 0                   | False      | None           | None             | None               | 6      
1  | gemini     | 9000        | 9000          | 20             | 34                  | False      | None           | None             | None               | 6      
```

### SQL QUERY 4.3 - Datos api_bundleapiextra (limit 5)
```sql
SELECT * FROM api_bundleapiextra LIMIT 5;
```
```text
id | servicio | activa | comprada_en                      | pago_id      | api_key_id | usuario_id
---+----------+--------+----------------------------------+--------------+------------+-----------
1  | gemini   | True   | 2026-05-08 22:02:28.894051+00:00 | manual_admin | 65         | 6         
2  | gemini   | True   | 2026-05-08 22:02:53.164362+00:00 | manual_admin | 66         | 6         
3  | gemini   | True   | 2026-05-08 22:03:10.513340+00:00 | manual_admin | 67         | 6         
4  | gemini   | True   | 2026-05-08 22:07:48.868722+00:00 | manual_admin | 68         | 6         
5  | gemini   | True   | 2026-05-08 22:46:04.585343+00:00 | manual_admin | 55         | 6         
```

### SQL QUERY 4.4 - Datos api_apibundle (limit 5)
```sql
SELECT * FROM api_apibundle LIMIT 5;
```
```text
id | nombre | status | notas | created_at | updated_at | key_elevenlabs_id | key_gemini_id | key_uploadpost_id
---+--------+--------+-------+------------+------------+-------------------+---------------+------------------
```

### SQL QUERY 4.5 - Datos api_apibundleassignment (limit 5)
```sql
SELECT * FROM api_apibundleassignment LIMIT 5;
```
```text
id | asignado_en | liberado_en | activo | bundle_id | usuario_id
---+-------------+-------------+--------+-----------+-----------
```

### SQL QUERY 4.6 - Datos api_suscripcion (limit 5)
```sql
SELECT * FROM api_suscripcion LIMIT 5;
```
```text
id | periodo_inicio | periodo_fin | properties_used | ai_used | images_used | videos_used | extra_credits | activa | agente_id | plan_id | mp_preapproval_id | mp_status | mp_subscription_id
---+----------------+-------------+-----------------+---------+-------------+-------------+---------------+--------+-----------+---------+-------------------+-----------+-------------------
```

## FILES CONTAINING 'mercadopago' OR 'webhook'

## SOURCE CODE

### File: .\api\urls.py
```python
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView
from . import views
from . import views_usage
from .views import (
    PropertyViewSet, GeneratedAssetViewSet, generar_guion, generar_listado, 
    RegisterView, LogoutView, DashboardView, ListadosView, generar_pdf, 
    PerfilView, ListadoDetalleView, generar_imagen_post, generar_imagen_story, 
    generar_email, serve_pdf_file, mp_checkout, mp_webhook, get_plan_info_mp,
    OnboardingView, video_status, publicar_instagram, send_otp, verify_otp,
    generar_video, obtener_terminos, obtener_politica_privacidad,
    plan_status, seleccionar_plan_free, test_upload_avatar, generar_carrusel,
    amenidades_presets, recuperar_password, confirmar_recuperacion,
    publicar_redes_sociales, proxy_pdf_view, proxy_pdf_thumbnail_view,
    generar_html, generar_escena, CustomTokenObtainPairView,
    upload_fotos_listado
)
from .views_admin import (
    admin_metricas, admin_usuarios_list, admin_usuario_cambiar_plan, admin_usuario_eliminar,
    admin_usuario_detalle, admin_usuarios_eliminados, admin_usuario_restaurar,
    admin_usuario_suspender, admin_apikeys_resumen, admin_apikeys_pool,
    admin_apikeys_pool_crear, admin_apikeys_pool_bulk, admin_apikeys_pool_detail, admin_apikeys_global,
    admin_pool_estado, admin_alerts_read, admin_health_check, admin_enviar_email,
    admin_bundles_list, admin_bundles_crear, admin_bundles_detail, admin_add_extra_api,
    admin_bundles_asignar, admin_bundles_liberar, admin_bundles_stats,
    admin_audio_music, admin_audio_music_detail, admin_audio_sfx, admin_audio_sfx_detail,
    admin_apikeys_auto_repair, admin_branding_watermark,
)

router = DefaultRouter()
router.register(r'properties', PropertyViewSet)
router.register(r'assets', GeneratedAssetViewSet)

urlpatterns = [
    path('auth/register/', RegisterView.as_view(), name='auth_register'),
    path('auth/login/', CustomTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('auth/login/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('auth/token/refresh/', TokenRefreshView.as_view(), name='token_refresh_alt'),
    path('auth/logout/', LogoutView.as_view(), name='auth_logout'),
    path('auth/perfil/', PerfilView.as_view(), name='auth_perfil'),
    path('auth/onboarding/', OnboardingView.as_view(), name='auth_onboarding'),
    path('auth/send-otp/', send_otp, name='auth_send_otp'),
    path('auth/verify-otp/', verify_otp, name='auth_verify_otp'),
    path('auth/plan-status/', plan_status, name='plan_status'),
    path('auth/seleccionar-plan-free/', seleccionar_plan_free, name='seleccionar_plan_free'),
    path('recuperar-password/', recuperar_password, name='recuperar_password'),
    path('confirmar-recuperacion/', confirmar_recuperacion, name='confirmar_recuperacion'),
    
    path('dashboard/', views.dashboard, name='dashboard'),
    path('listados/', ListadosView.as_view(), name='listados'),
    path('listados/<int:pk>/', ListadoDetalleView.as_view(), name='listado_detalle'),
    path('listados/upload-fotos/', upload_fotos_listado, name='upload_fotos_listado'),
    path('listados/<int:pk>/html/', generar_html, name='generar_html'),
    path('listados/<int:pk>/generar-video/', generar_video, name='generar_video'),
    path('listados/<int:listado_id>/pdf-proxy/', proxy_pdf_view, name='pdf_proxy'),
    path('listados/<int:listado_id>/pdf-thumbnail/', proxy_pdf_thumbnail_view, name='pdf_thumbnail'),
    path('descargar-pdf/<int:listado_id>/', views.descargar_pdf, name='descargar_pdf'),

    path('', include(router.urls)),
    path('generar-guion/', generar_guion, name='generar_guion'),
    path('generar-escena/', generar_escena, name='generar_escena'),
    path('generar-listado/', generar_listado, name='generar_listado'),
    path('generar-pdf/', generar_pdf, name='generar_pdf'),
    path('generar-imagen-post/', generar_imagen_post, name='generar_imagen_post'),
    path('generar-imagen-story/', generar_imagen_story, name='generar_imagen_story'),
    path('generar-email/', generar_email, name='generar_email'),
    path('publicar-instagram/', publicar_instagram, name='publicar_instagram'),
    path('publicar-redes/', publicar_redes_sociales, name='publicar_redes_sociales'),
    path('pdf/<str:uuid_str>/', serve_pdf_file, name='serve_pdf'),
    path('video-status/<int:listado_id>/', video_status, name='video_status'),
    
    path('mp/checkout/', mp_checkout,  name='mp_checkout'),
    path('mp/webhook/',  mp_webhook,   name='mp_webhook'),
    path('mp/plan/',     get_plan_info_mp,       name='mp_plan_info'),

    # Legal
    path('terminos-y-condiciones/', obtener_terminos, name='obtener_terminos'),
    path('politica-privacidad/', obtener_politica_privacidad, name='obtener_politica_privacidad'),

    # Test endpoints
    path('test-upload/', test_upload_avatar, name='test_upload_avatar'),
    path('generar-carrusel/', generar_carrusel, name='generar_carrusel'),
    path('amenidades-presets/', amenidades_presets, name='amenidades_presets'),

    # Admin Dash
    path('admin/stats/', admin_metricas),
    path('admin/usuarios/', admin_usuarios_list),
    path('admin/usuarios-eliminados/', admin_usuarios_eliminados),
    path('admin/usuarios/<int:user_id>/', admin_usuario_eliminar),
    path('admin/usuarios/<int:user_id>/restaurar/', admin_usuario_restaurar),
    path('admin/usuarios/<int:user_id>/detalle/', admin_usuario_detalle),
    path('admin/usuarios/<int:user_id>/cambiar-plan/', admin_usuario_cambiar_plan),
    path('admin/usuarios/<int:user_id>/suspender/', admin_usuario_suspender),
    path('admin/usuarios/<int:user_id>/email/', admin_enviar_email),
    path('admin/users/<int:user_id>/add-extra/', admin_add_extra_api),
    path('admin/listados/', views.admin_listados),
    path('admin/assets/', views.admin_assets),
    path('admin/pagos/', views.admin_pagos),
    
    # API Keys & Pool
    path('admin/apikeys/resumen/', admin_apikeys_resumen),
    path('admin/apikeys/pool/', admin_apikeys_pool),
    path('admin/apikeys/pool/crear/', admin_apikeys_pool_crear),
    path('admin/apikeys/pool/bulk/', admin_apikeys_pool_bulk),
    path('admin/apikeys/pool/<int:key_id>/', admin_apikeys_pool_detail),
    path('admin/apikeys/pool/<int:key_id>/detalle/', admin_apikeys_pool_detail),
    path('admin/apikeys/global/', admin_apikeys_global),
    path('admin/apikeys/pool/auto-repair/', admin_apikeys_auto_repair),
    path('admin/pool/estado/', admin_pool_estado),
    path('admin/pool/listar/', admin_apikeys_pool), # Alias
    path('admin/alerts/<int:alert_id>/read/', admin_alerts_read),
    path('admin/health-check/', admin_health_check),

    # Conexiones Redes (UploadPost)
    path('conexiones/init/', views.conexiones_init),
    path('conexiones/estado/', views.conexiones_estado),
    path('conexiones/eliminar/', views.conexiones_eliminar),

    # Debug / Diagnóstico
    path('debug/email-check/', views.debug_email_check, name='debug_email_check'),
    path('debug/email-send/',  views.debug_email_send,  name='debug_email_send'),
    path('debug/uploadpost/<str:username>/', views.debug_uploadpost, name='debug_uploadpost'),

    # Uso de APIs
    path('auth/mi-uso/', views_usage.mi_uso_apis, name='mi_uso_apis'),
    path('admin/uso-global/', views_usage.admin_uso_global, name='admin_uso_global'),

    # API Bundles
    path('admin/bundles/', admin_bundles_list),
    path('admin/bundles/crear/', admin_bundles_crear),
    path('admin/bundles/stats/', admin_bundles_stats),
    path('admin/bundles/<int:bundle_id>/', admin_bundles_detail),
    path('admin/bundles/<int:bundle_id>/asignar/', admin_bundles_asignar),
    path('admin/bundles/<int:bundle_id>/liberar/', admin_bundles_liberar),

    # Librería de Audio
    path('admin/audio/music/', admin_audio_music),
    path('admin/audio/music/<int:pk>/', admin_audio_music_detail),
    path('admin/audio/sfx/', admin_audio_sfx),
    path('admin/audio/sfx/<int:pk>/', admin_audio_sfx_detail),
    path('admin/branding/watermark/', admin_branding_watermark),

    # Notificaciones
    path('notificaciones/', views.listar_notificaciones),
    path('notificaciones/<int:notif_id>/leer/', views.marcar_notificacion_leida),
    path('notificaciones/leer-todas/', views.marcar_todas_leidas),
    path('cuota-ia/', views.estado_cuota_ia),
    path('mp/checkout-extra/', views.mp_checkout_api_extra),
    path('debug/quota/', views.debug_quota),
]
```

### File: .\api\views.py
```python
from rest_framework import viewsets, status
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, AllowAny, IsAdminUser
from rest_framework_simplejwt.tokens import RefreshToken
from django.utils import timezone
from django.db.models import Sum
import requests
from django.http import HttpResponse, StreamingHttpResponse
from decouple import config
import cloudinary
import cloudinary.uploader
from api.services.almacenamiento import AlmacenamientoCloudinary
import logging

logger = logging.getLogger(__name__)

from .models import (
    Property, GeneratedAsset, Listado, OTPCode,
    TerminosCondiciones, PoliticaPrivacidad
)
from .serializers import (
    PropertySerializer, GeneratedAssetSerializer, RegisterSerializer,
    TerminosCondicionesSerializer, PoliticaPrivacidadSerializer
)
from .tasks import run_asset_generation
from .ai_services import call_groq_api, call_gemini_api, smart_call, GeminiQuotaExhaustedError
from .utils import crear_notificacion
from django.template.loader import render_to_string
from .services.render_engine import render_html_to_image
from .plan_utils import puede_generar, incrementar_uso

def actualizar_resultados_listado(listado, tipo, resultado):
    """
    Guarda el resultado (URL, caption, etc) dentro del JSON de datos del listado.
    Esto permite persistencia entre sesiones.
    """
    if not listado: return
    if not isinstance(listado.datos, dict):
        listado.datos = {}
    
    if 'resultados' not in listado.datos:
        listado.datos['resultados'] = {}
    
    listado.datos['resultados'][tipo] = resultado
    listado.save(update_fields=['datos'])

LIMITES_PLAN = {
    'free':     {'listados_mes': 10},
    'starter':  {'listados_mes': 40},
    'pro':      {'listados_mes': 150},
    'scale':    {'listados_mes': 999999},
    'business': {'listados_mes': 999999},
}

def verificar_limite_plan(agent):
    from datetime import datetime
    plan = getattr(agent, 'plan_nombre', 'free')
    limite = LIMITES_PLAN.get(plan, LIMITES_PLAN['free'])
    
    ahora = datetime.now()
    listados_mes = Listado.objects.filter(
        agente=agent,
        creado_en__year=ahora.year,
        creado_en__month=ahora.month
    ).count()
    
    if listados_mes >= limite['listados_mes']:
        return False, listados_mes, limite['listados_mes']
    return True, listados_mes, limite['listados_mes']

from io import BytesIO
from django.template.loader import get_template

from django.http import HttpResponse

import base64
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import io
import tempfile
import uuid
import os
import time

def generar_qr_url(telefono, tipo_propiedad='', ciudad='', operacion='', precio='', moneda=''):
    import urllib.parse, urllib.request, base64
    # Limpiar teléfono: solo dígitos
    tel_limpio = ''.join(filter(str.isdigit, str(telefono)))
    # Si no empieza con código de país, asumir Argentina (+54)
    if tel_limpio and not tel_limpio.startswith('54'):
        tel_limpio = '54' + tel_limpio
    # Armar mensaje profesional
    detalle = f"{tipo_propiedad} en {ciudad}".strip(' en') if tipo_propiedad or ciudad else "propiedad"
    precio_str = f" por {moneda} {precio}" if precio else ""
    op_str = f" en {operacion.lower()}" if operacion else ""
    mensaje = f"Hola! Me interesa {detalle}{op_str}{precio_str}. ¿Podés darme más información?"
    # Armar URL de WhatsApp
    wa_url = f"https://wa.me/{tel_limpio}?text={urllib.parse.quote(mensaje)}"
    # Generar QR de la URL de WhatsApp
    qr_api = f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={urllib.parse.quote(wa_url)}"
    try:
        with urllib.request.urlopen(qr_api, timeout=5) as resp:
            png_bytes = resp.read()
        b64 = base64.b64encode(png_bytes).decode()
        return f"data:image/png;base64,{b64}"
    except Exception as e:
        print(f"[QR] Error: {e}")
        return ''

def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip

from rest_framework_simplejwt.views import TokenObtainPairView
from api.models import BannedIP, Agent

class CustomTokenObtainPairView(TokenObtainPairView):
    def post(self, request, *args, **kwargs):
        ip = get_client_ip(request)
        if BannedIP.objects.filter(ip_address=ip).exists():
            return Response({'detail': 'Tu IP ha sido bloqueada. Contacta al soporte.'}, status=status.HTTP_403_FORBIDDEN)
        
        response = super().post(request, *args, **kwargs)
        if response.status_code == 200:
            # Login successful
            email = request.data.get('email')
            user_agent = request.META.get('HTTP_USER_AGENT', '')
            try:
                agent = Agent.objects.get(email=email)
                agent.last_login_ip = ip
                agent.last_login_user_agent = user_agent
                agent.save(update_fields=['last_login_ip', 'last_login_user_agent'])
            except Agent.DoesNotExist:
                pass
        return response

class RegisterView(APIView):
    permission_classes = [AllowAny]
    def post(self, request):
        from datetime import timedelta
        from django.utils import timezone
        email = request.data.get('email', '').strip().lower()
        
        ip = get_client_ip(request)
        if BannedIP.objects.filter(ip_address=ip).exists():
            return Response({'error': 'Tu IP ha sido bloqueada. No podés crear cuentas.'}, status=status.HTTP_403_FORBIDDEN)
        
        # Verificar blacklist de emails baneados permanentemente
        from .models import Agent, BannedEmail
        if BannedEmail.objects.filter(email=email).exists():
            return Response({"error": "Esta cuenta ha sido inhabilitada permanentemente. No podés registrarte con este email."}, status=403)
        
        # Validar email duplicado
        if Agent.objects.filter(email=email).exists():
            return Response({"error": "Este email ya está registrado. ¿Olvidaste tu contraseña?"}, status=400)

        otp_verificado = OTPCode.objects.filter(
            email=email,
            verified=True,
            created_at__gte=timezone.now() - timedelta(hours=1)
        ).exists()
        if not otp_verificado:
            return Response({"error": "Debés verificar tu email primero"}, status=400)
            
        serializer = RegisterSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            
            # Asignar plan free por defecto
            user.plan_nombre = 'free'
            user.plan_activo = True
            user.plan_seleccionado = True
            user.save()
            
            # TAREA 3: Consumir el OTP para que no pueda reutilizarse
            otp_usado = OTPCode.objects.filter(
                email=email,
                verified=True,
                created_at__gte=timezone.now() - timedelta(hours=1)
            ).order_by('-created_at').first()
            if otp_usado:
                otp_usado.verified = False
                otp_usado.code_hash = 'USED'
                otp_usado.save()

            user.last_login_ip = ip
            user.last_login_user_agent = request.META.get('HTTP_USER_AGENT', '')
            user.save(update_fields=['last_login_ip', 'last_login_user_agent'])
            refresh = RefreshToken.for_user(user)
            return Response({
                'access': str(refresh.access_token),
                'refresh': str(refresh),
            }, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class LogoutView(APIView):
    permission_classes = [IsAuthenticated]
    def post(self, request):
        try:
            refresh_token = request.data["refresh_token"]
            token = RefreshToken(refresh_token)
            token.blacklist()
            return Response(status=status.HTTP_205_RESET_CONTENT)
        except Exception as e:
            return Response(status=status.HTTP_400_BAD_REQUEST)

class PropertyViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    queryset = Property.objects.none()
    serializer_class = PropertySerializer

    def get_queryset(self):
        return Property.objects.filter(agent=self.request.user)

    @action(detail=True, methods=['post'])
    def generate_assets(self, request, pk=None):
        property_instance = self.get_object()
        
        # Trigger Celery Task
        run_asset_generation.delay(property_instance.id)

        return Response({
            'message': 'Asset generation triggered successfully.',
            'status': 'PROCESSING'
        }, status=status.HTTP_202_ACCEPTED)

class GeneratedAssetViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated]
    queryset = GeneratedAsset.objects.none()
    serializer_class = GeneratedAssetSerializer

    def get_queryset(self):
        return GeneratedAsset.objects.filter(agent=self.request.user)
import os
import concurrent.futures

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generar_guion(request):
    # TODO: re-habilitar cuando el sistema de planes esté estable
    # if not puede_generar(request.user, 'ai'):
    #     return Response({
    #         "error": "limite_alcanzado", 
    #         "mensaje": "Superaste el límite de tu plan. Actualizá tu suscripción.",
    #         "upgrade_url": "/precios"
    #     }, status=status.HTTP_403_FORBIDDEN)

    data = request.data
    tipo_video = data.get('tipoVideo', 'reel')
    tipo = data.get('tipoPropiedad', 'Propiedad')
    ciudad = data.get('ciudad', '')
    operacion = data.get('operacion', 'Venta')
    moneda = data.get('moneda', 'USD')
    precio = data.get('precio', '')
    recamaras = str(data.get('recamaras', '') or data.get('habitaciones', ''))
    banos = str(data.get('banos', '') or data.get('bathrooms', ''))
    superficie = str(data.get('superficieCubierta', '') or data.get('metros', ''))
    voz = data.get('voz', 'femenina')          # 'masculina' | 'femenina'
    tono = data.get('tono', 'profesional')     # 'profesional' | 'lujo' | 'energetico'
    voiceover = data.get('voiceover', False)   # bool
    contexto_adicional = data.get('contextoAdicional', '')

    # Mapear tono a instrucciones narrativas
    tono_map = {
        'profesional': 'profesional y formal, directo, transmite confianza y seriedad',
        'lujo':        'de lujo y exclusividad, sofisticado, evoca aspiración y premium lifestyle, usa vocabulario refinado',
        'energetico':  'dinámico y energético, entusiasta, usa frases cortas e impactantes, genera urgencia'
    }
    tono_instrucciones = tono_map.get(tono, tono_map['profesional'])

    # Narrador según voz
    narrador_instrucciones = (
        'con voz masculina en mente: frases firmes, directas, con autoridad'
        if voz == 'masculina' else
        'con voz femenina en mente: frases cálidas, cercanas, invitadoras'
    )

    # Intentar IA solo si hay keys Y con timeout estricto de 5s
    descripcion_ia = None
    GEMINI_KEY = os.environ.get('GEMINI_API_KEY', '')
    GROQ_KEY = os.environ.get('GROQ_API_KEY', '')

    if GEMINI_KEY or GROQ_KEY:
        palabras_por_escena = "25-38 palabras" if tipo_video == 'reel' else "50-75 palabras"
        palabras_total = "100-150 palabras" if tipo_video == 'reel' else "200-300 palabras"
        contexto_extra = f"\nENFOQUE ADICIONAL DEL CLIENTE: {contexto_adicional}" if contexto_adicional else ''
        prompt = f"""Sos un copywriter inmobiliario experto.
Generá un guión PROFESIONAL para video tipo {tipo_video}.

PROPIEDAD:
- Tipo: {tipo}
- Operación: {operacion}
- Ubicación: {ciudad}
- Precio: {moneda} {precio}
- Recámaras: {recamaras}
- Baños: {banos}

ESTILO DE NARRACIÓN:
- Tono: {tono_instrucciones}
- Narrador: {narrador_instrucciones}
- Tipo de video: {tipo_video.upper()} — {'Tour inmersivo y narrado, guía al espectador por la propiedad' if tipo_video == 'tour' else 'Reel dinámico, impacto visual rápido'}{contexto_extra}

REQUISITOS:
- Genera EXACTAMENTE 4 escenas
- Cada escena: {palabras_por_escena} (texto persuasivo y descriptivo)
- Total del guión: {palabras_total}
- Formato: JSON puro

ESTRUCTURA:
[
  {{"nombre":"Apertura","texto":"...","icono":"🏠"}},
  {{"nombre":"Detalles","texto":"...","icono":"✨"}},
  {{"nombre":"Ubicación","texto":"...","icono":"📍"}},
  {{"nombre":"CTA","texto":"...","icono":"📞"}}
]

RESPONDE SOLO JSON, SIN PREAMBLE."""
        try:
            with concurrent.futures.ThreadPoolExecutor() as ex:
                future = ex.submit(call_gemini_api, prompt, agente=request.user)
                descripcion_ia = future.result(timeout=15)
        except Exception:
            descripcion_ia = None

    # Fallback local — siempre 4 escenas con rangos exactos de palabras
    if tipo_video == 'tour':
        # Tour narrado: 6 escenas arquitectónicas (porta el estilo de LEADBOOK UP)
        escenas_default = [
            {"nombre": "Fachada", "icono": "🏠",
             "texto": f"Bienvenidos a esta {tipo} en {operacion} en {ciudad}. Una oportunidad única en el mercado inmobiliario actual. Precio: {moneda} {precio}."},
            {"nombre": "Sala", "icono": "🛋️",
             "texto": "Amplios espacios interiores diseñados para el confort familiar. Luz natural, alturas generosas y un diseño que invita a disfrutar cada rincón."},
            {"nombre": "Cocina", "icono": "🍳",
             "texto": "Cocina funcional con terminaciones de primera calidad, espacios de guardado y distribución inteligente para el uso diario."},
            {"nombre": "Recámara", "icono": "🛏️",
             "texto": f"{'Con ' + str(recamaras) + ' recámaras y ' + str(banos) + ' baños.' if recamaras else 'Dormitorios luminosos para el descanso ideal.'} Acabados de primera línea{(', superficie cubierta de ' + superficie + ' m²') if superficie else ''}."},
            {"nombre": "Exteriores", "icono": "🌿",
             "texto": f"Espacios exteriores que complementan una vida plena en {ciudad}. Zonas de esparcimiento, acceso a servicios y conectividad inmejorable."},
            {"nombre": "Cierre", "icono": "📞",
             "texto": f"Precio: {moneda} {precio}. No dejes que alguien más tome esta decisión. Contactanos hoy mismo y agendá tu visita personalizada. ¡Te esperamos!"}
        ]
    else:  # reel rápido: 100-150 palabras totales (25-38 palabras por escena)
        escenas_default = [
            {"nombre": "Apertura", "icono": "⚡",
             "texto": f"✨ {tipo} en {operacion} en {ciudad}. Precio: {moneda} {precio}. Una oportunidad única en el mercado inmobiliario actual. No te la pierdas."},
            {"nombre": "Características", "icono": "🏠",
             "texto": f"{recamaras} recámaras · {banos} baños{(' · ' + superficie + ' m²') if superficie else ''}. Espacios amplios, luminosos y diseñados para el máximo confort. Acabados de primera categoría."},
            {"nombre": "Ubicación", "icono": "📍",
             "texto": f"Estratégicamente ubicado en {ciudad}. Acceso a los mejores servicios, comercios, transporte y zonas de esparcimiento. Todo lo que necesitás, cerca de vos."},
            {"nombre": "Contacto", "icono": "📞",
             "texto": f"¡El hogar que soñabas está en {ciudad}! Contactanos ahora mismo, agendá tu visita y hacelo tuyo antes de que sea tarde."}
        ]


    # Parsear respuesta de IA si vino bien
    escenas_finales = escenas_default
    if descripcion_ia:
        from .plan_utils import registrar_uso
        registrar_uso(request.user, 'ai')
        try:
            import json as _json
            parsed = _json.loads(descripcion_ia)
            if isinstance(parsed, list) and len(parsed) >= 4:
                escenas_finales = parsed
        except Exception:
            pass

    return Response({'escenas': escenas_finales, 'tipo_video': tipo_video})

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generar_listado(request):
    # TODO: re-habilitar cuando el sistema de planes esté estable
    # if not puede_generar(request.user, 'ai'):
    #     return Response({
    #         "error": "limite_alcanzado", 
    #         "mensaje": "Superaste el límite de tu plan. Actualizá tu suscripción.",
    #         "upgrade_url": "/precios"
    #     }, status=status.HTTP_403_FORBIDDEN)
            
    prompt_text = request.data.get("prompt", "")
    if not prompt_text:
        return Response({"error": "No prompt provided. Please pass a 'prompt' field in the JSON body."}, status=status.HTTP_400_BAD_REQUEST)
        
    system_prompt = "Sos un as copywriter de real estate. Escribí descripciones profesionales, persuasivas y completas (listados) para propiedades en venta o alquiler en español."

    try:
        result = call_groq_api(prompt_text, system_prompt=system_prompt)
    except Exception as e_groq:
        # Fallback: intentar con Gemini si Groq falla
        try:
            result = call_gemini_api(prompt_text, system_prompt=system_prompt, agente=request.user)
        except Exception as e_gem:
            return Response({
                "error": "IA no disponible",
                "detalle": f"Groq: {e_groq} | Gemini: {e_gem}"
            }, status=status.HTTP_503_SERVICE_UNAVAILABLE)

    if request.user.is_authenticated:
        incrementar_uso(request.user, 'ai')
    return Response({"generated_text": result}, status=status.HTTP_200_OK)

class DashboardView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        now = timezone.now()
        start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        
        listados = Listado.objects.filter(agente=user)
        listados_este_mes = listados.filter(creado_en__gte=start_of_month).count()
        total_generados = listados.count()
        
        videos_creados = listados.aggregate(total_videos=Sum('videos_creados'))['total_videos'] or 0

        listados_recientes = listados.order_by('-creado_en')[:5].values(
            'id', 'titulo', 'tipo_propiedad', 'ciudad', 'precio', 'creado_en', 'datos', 'video_url', 'video_status'
        )

        susc = get_suscripcion(user)
        plan = susc.plan

        return Response({
            "nombre_inmobiliaria": getattr(user, 'nombre_inmobiliaria', None),
            "logo_url": getattr(user, 'logo_url', None),
            "listados_este_mes": listados_este_mes,
            "total_generados": total_generados,
            "videos_creados": videos_creados,
            "conexiones_activas": 0,
            "listados_recientes": list(listados_recientes),
            "plan": plan.nombre,
            "plan_limites": {
                "properties_per_month": plan.properties_per_month,
                "ai_generations": plan.ai_generations,
                "image_generations": plan.image_generations,
                "video_generations": plan.video_generations,
                "branding": plan.branding
            },
            "uso_actual": {
                "properties_used": susc.properties_used,
                "ai_used": susc.ai_used,
                "images_used": susc.images_used,
                "videos_used": susc.videos_used
            }
        })

class PerfilView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        return Response({
            "email": user.email,
            "nombre": user.nombre,
            "nombre_inmobiliaria": getattr(user, 'nombre_inmobiliaria', None),
            "agencia": getattr(user, 'agencia', None),
            "logo_url": getattr(user, 'logo_url', None),
            "telefono": getattr(user, 'telefono', None),
            "nicho": getattr(user, 'nicho', None),
            "pais": getattr(user, 'pais', None),
            "nacionalidad": getattr(user, 'nacionalidad', None),
            "sitio_web": getattr(user, 'sitio_web', None),
            "bio": getattr(user, 'bio', None),
            "meta_access_token": getattr(user, 'meta_access_token', None),
            "meta_instagram_account_id": getattr(user, 'meta_instagram_account_id', None),
            "agentes_asociados": getattr(user, 'agentes_asociados', []),
            "plan_nombre": getattr(user, 'plan_nombre', 'starter'),
            "is_staff": user.is_staff,
            "plan_seleccionado": user.plan_seleccionado,
            "plan_activo": user.plan_activo,
        })

    def put(self, request):
        from .models import Agent
        user = Agent.objects.get(id=request.user.id)
        data = request.data
        
        if 'nombre_inmobiliaria' in data:
            user.nombre_inmobiliaria = data['nombre_inmobiliaria']
        elif 'nombreInmobiliaria' in data:
            user.nombre_inmobiliaria = data['nombreInmobiliaria']
            
        if 'logo_url' in data:
            user.logo_url = data['logo_url']
        elif 'logoUrl' in data:
            user.logo_url = data['logoUrl']
            
        agentes_input = data.get('agentes_asociados')
        if agentes_input is None:
            agentes_input = data.get('agentesAsociados')
            
        if agentes_input is not None:
            # Si el frontend envía un string en vez de un array JSON, lo parseamos
            import json
            if isinstance(agentes_input, str):
                try:
                    agentes_input = json.loads(agentes_input)
                except json.JSONDecodeError:
                    pass
            user.agentes_asociados = agentes_input
            
        if 'meta_access_token' in data:
            user.meta_access_token = data['meta_access_token']
        if 'meta_instagram_account_id' in data:
            user.meta_instagram_account_id = data['meta_instagram_account_id']
        if 'telefono' in data:
            user.telefono = data['telefono']
        if 'agencia' in data:
            user.agencia = data['agencia']
        if 'nicho' in data:
            user.nicho = data['nicho']
        if 'pais' in data:
            user.pais = data['pais']
        if 'nacionalidad' in data:
            user.nacionalidad = data['nacionalidad']
        if 'sitio_web' in data:
            user.sitio_web = data['sitio_web']
        if 'bio' in data:
            user.bio = data['bio']
            
        user.save()
        return Response({
            "message": "Perfil actualizado exitosamente",
            "email": user.email,
            "nombre": user.nombre,
            "nombre_inmobiliaria": getattr(user, 'nombre_inmobiliaria', None),
            "agencia": getattr(user, 'agencia', None),
            "logo_url": getattr(user, 'logo_url', None),
            "telefono": getattr(user, 'telefono', None),
            "nicho": getattr(user, 'nicho', None),
            "pais": getattr(user, 'pais', None),
            "nacionalidad": getattr(user, 'nacionalidad', None),
            "sitio_web": getattr(user, 'sitio_web', None),
            "bio": getattr(user, 'bio', None),
            "meta_access_token": getattr(user, 'meta_access_token', None),
            "meta_instagram_account_id": getattr(user, 'meta_instagram_account_id', None),
            "agentes_asociados": getattr(user, 'agentes_asociados', []),
            "plan_nombre": getattr(user, 'plan_nombre', 'starter')
        }, status=status.HTTP_200_OK)

from .services.instagram_service import publicar_post, publicar_story, publicar_carrusel, publicar_media_upload_api
from django.conf import settings

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def publicar_instagram(request):
    try:
        data = request.data
        tipo = data.get('tipo', 'post')
        imagen_url = data.get('imagen_url', '')
        imagenes_urls = data.get('imagenes_urls', [])
        caption = data.get('caption', '')
        
        user = request.user
        access_token = user.meta_access_token or getattr(settings, 'META_ACCESS_TOKEN', '')
        account_id = user.meta_instagram_account_id or getattr(settings, 'META_INSTAGRAM_ACCOUNT_ID', '')
        
        if not access_token or not account_id:
            return Response({"success": False, "error": "Credenciales de Instagram no configuradas."}, status=status.HTTP_400_BAD_REQUEST)
            
        if tipo == 'post':
            result = publicar_post(imagen_url, caption, access_token, account_id)
        elif tipo == 'story':
            result = publicar_story(imagen_url, access_token, account_id)
        elif tipo == 'carrusel':
            result = publicar_carrusel(imagenes_urls, caption, access_token, account_id)
        else:
            return Response({"success": False, "error": "Tipo invalido (post/story/carrusel)"}, status=status.HTTP_400_BAD_REQUEST)
            
        if result.get('success'):
            return Response(result, status=status.HTTP_200_OK)
        else:
            return Response(result, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    except Exception as e:
        return Response({"success": False, "error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def publicar_redes_sociales(request):
    """
    Endpoint unificado para publicar contenido en redes sociales vía Upload Post API.
    Tipos soportados: image, video, carousel, document (PDF).
    """
    try:
        data = request.data
        media_type = data.get('media_type', 'image') # image, video, carousel, document
        caption = data.get('caption', '')
        
        # URLs de contenido
        image_url = data.get('image_url')
        video_url = data.get('video_url')
        document_url = data.get('document_url')
        images = data.get('images', []) # array de URLs para carrusel
        
        # Opciones extra
        platforms = data.get('platforms') # ej: ['instagram', 'facebook', 'youtube']
        scheduled_at = data.get('scheduled_at') # string ISO 8601
        
        user = request.user
        
        # Llamar al servicio unificado de Upload Post
        result = publicar_media_upload_api(
            media_type=media_type,
            caption=caption,
            image_url=image_url,
            video_url=video_url,
            images=images,
            document_url=document_url,
            platforms=platforms,
            scheduled_at=scheduled_at,
            agente=user
        )
        
        if result.get('success'):
            # --- Añadir tracking manual de uso para UploadPost ---
            try:
                from api.pool_manager import get_api_key
                from api.models import APIKey
                from django.utils import timezone
                key_str = get_api_key(user, 'uploadpost')
                if key_str:
                    k = APIKey.objects.filter(api_key=key_str).first()
                    if k:
                        k.requests_today += 1
                        k.requests_this_month += 1
                        k.total_requests += 1
                        k.last_used_at = timezone.now()
                        k.save()
            except Exception as trk_e:
                print(f"[UploadPost Tracking Error]: {trk_e}")
            # -----------------------------------------------------
            
            return Response(result, status=status.HTTP_200_OK)
        else:
            return Response(result, status=status.HTTP_400_BAD_REQUEST)
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        return Response({"success": False, "error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generar_carrusel(request):
    """Genera 5 imágenes de carrusel y un caption con Gemini."""
    try:
        user = request.user
        # TODO: re-habilitar cuando el sistema de planes esté estable
        # if not puede_generar(user, 'image'):
        #      return Response({
        #         "error": "limite_alcanzado", 
        #         "mensaje": "Superaste el límite de tu plan. Actualizá tu suscripción.",
        #         "upgrade_url": "/precios"
        #     }, status=status.HTTP_403_FORBIDDEN)

        data = request.data
        fotos = data.get('fotosRecorrido', [])
        if not isinstance(fotos, list): fotos = []
        
        # Aseguramos tener 5 fotos (repetimos si es necesario)
        portada = data.get('portadaUrl')
        images_to_use = []
        if portada: images_to_use.append(portada)
        images_to_use.extend([f.get('url') if isinstance(f, dict) else f for f in fotos if f])
        
        # Si no hay imágenes, generamos slides de diseño puro (sin foto de fondo)
        # Pasamos None para que generate_social_image use fondo negro/degradado
        if not images_to_use:
            images_to_use = [None] * 5
        
        while len(images_to_use) < 5:
            images_to_use.append(images_to_use[len(images_to_use) % len(images_to_use)])
            
        slides_urls = []
        slides_content = [
            {"headline": data.get('tipoPropiedad', 'Propiedad'), "subheadline": f"Una oportunidad única en {data.get('ciudad', '')}"},
            {"headline": "Espacios", "subheadline": "Diseño y amplitud pensados para tu máximo confort."},
            {"headline": "Detalles", "subheadline": "Terminaciones de calidad que marcan la diferencia."},
            {"headline": "Inversión", "subheadline": f"Tu próximo hogar por solo {data.get('moneda', 'USD')} {data.get('precio', '')}"},
            {"headline": "Contacto", "subheadline": "No dejes pasar esta oportunidad. Contactanos hoy."}
        ]

        for i in range(5):
            # Preparar contexto para el slide actual
            context = {
                "portada_url": images_to_use[i],
                "headline": slides_content[i]["headline"],
                "subheadline": slides_content[i]["subheadline"],
                "slide_number": i + 1,
                "total_slides": 5,
                "logo_url": data.get('logoAgenciaUrl')
            }
            
            # Renderizar el slide con Playwright
            html_content = render_to_string('renders/carousel.html', context)
            image_stream = render_html_to_image(html_content, 1080, 1350)
            
            # Subir a Cloudinary via Almacenamiento centralizado
            try:
                image_stream.seek(0)
                listado_id_val = data.get('listado_id')
                url = AlmacenamientoCloudinary.guardar_slide_carrusel(
                    image_stream, 
                    user_id=request.user.id, 
                    listado_id=listado_id_val,
                    slide_index=i + 1
                )
                if not url:
                    raise Exception('Almacenamiento devolvió None')
                slides_urls.append(url)
            except Exception as cloud_err:
                print(f"[DEBUG] ERROR Almacenamiento Slide {i+1}: {str(cloud_err)}")
                return Response({"error": f"Error subiendo slide {i+1}"}, status=500)

        # Generar Caption con Gemini (con fallback a Groq)
        prompt_text = f"Escribí un caption para un carrusel de Instagram de una propiedad: {data.get('tipoPropiedad', 'Propiedad')} en {data.get('ciudad', '')} por {data.get('precio', '')}. Enfocado en vender el estilo de vida y llamar a la acción. Usá emojis y hashtags."
        caption = smart_call(prompt_text, system_prompt="Sos un experto en marketing inmobiliario digital.", agente=user)

        # PERSISTENCIA: Guardar en el listado
        if listado_id_val:
            from .models import Listado
            listado_obj = Listado.objects.filter(id=listado_id_val, agente=request.user).first()
            actualizar_resultados_listado(listado_obj, 'carrusel', {"slides": slides_urls, "caption": caption})

        if user.is_authenticated:
            incrementar_uso(user, 'image')

        return Response({
            "slides": slides_urls,
            "caption": caption
        }, status=status.HTTP_200_OK)
    except GeminiQuotaExhaustedError as e:
        crear_notificacion(
            request.user,
            'quota_agotada',
            'Alcanzaste el 100% de tu uso de IA',
            'Tus créditos de generación de contenido se agotaron. Se resetean automáticamente a medianoche.'
        )
        return Response({"error": "cuota_ia_agotada", "mensaje": str(e)}, status=status.HTTP_429_TOO_MANY_REQUESTS)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return Response({"error": str(e), "detalle": traceback.format_exc()}, status=500)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def test_upload_avatar(request):
    try:
        file = request.FILES.get('file')
        if not file:
            return Response({'error': 'No file provided'}, status=400)
        url = AlmacenamientoCloudinary.guardar_avatar(file, user_id=request.user.id)
        if not url:
            return Response({'error': 'Error al subir imagen'}, status=500)
        return Response({'url': url})
    except Exception as e:
        return Response({'error': str(e)}, status=500)


class OnboardingView(APIView):
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        return self.put(request)

    def put(self, request):
        user = request.user
        data = request.data
        
        if 'nombre_inmobiliaria' in data:
            user.nombre_inmobiliaria = data['nombre_inmobiliaria']
        elif 'nombreInmobiliaria' in data:
            user.nombre_inmobiliaria = data['nombreInmobiliaria']
            
        if 'logo_url' in data:
            user.logo_url = data['logo_url']
        elif 'logoUrl' in data:
            user.logo_url = data['logoUrl']
            
        if 'nicho' in data:
            user.nicho = data['nicho']
        if 'pais' in data:
            user.pais = data['pais']
            
        if 'telefono' in data:
            user.telefono = data['telefono']
        if 'agencia' in data:
            user.agencia = data['agencia']
        if 'nacionalidad' in data:
            user.nacionalidad = data['nacionalidad']
        if 'sitio_web' in data:
            user.sitio_web = data['sitio_web']
        elif 'sitioWeb' in data:
            user.sitio_web = data['sitioWeb']
        if 'bio' in data:
            user.bio = data['bio']
            
        user.save()
        return Response({
            "email": user.email,
            "nombre": user.nombre,
            "nombre_inmobiliaria": getattr(user, 'nombre_inmobiliaria', None),
            "logo_url": getattr(user, 'logo_url', None),
            "telefono": getattr(user, 'telefono', None),
            "nicho": getattr(user, 'nicho', None),
            "pais": getattr(user, 'pais', None),
            "nacionalidad": getattr(user, 'nacionalidad', None),
            "sitio_web": getattr(user, 'sitio_web', None),
            "bio": getattr(user, 'bio', None),
            "agentes_asociados": getattr(user, 'agentes_asociados', []),
            "plan_nombre": getattr(user, 'plan_nombre', 'starter')
        }, status=status.HTTP_200_OK)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def video_status(request, listado_id):
    try:
        from .models import Listado
        listado = Listado.objects.get(id=listado_id, agente=request.user)
        return Response({
            "status": listado.video_status,
            "video_url": listado.video_url
        }, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({"error": "Listado no encontrado"}, status=status.HTTP_404_NOT_FOUND)

class ListadosView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Devuelve todos los listados del usuario logueado"""
        listados = Listado.objects.filter(agente=request.user)
        data = []
        for listado in listados:
            data.append({
                'id': listado.id,
                'titulo': listado.titulo,
                'tipo_propiedad': listado.tipo_propiedad,
                'ciudad': listado.ciudad,
                'precio': listado.precio,
                'creado_en': listado.creado_en,
                'videos_creados': listado.videos_creados,
                'video_url': listado.video_url,
                'video_status': listado.video_status,
                'datos': listado.datos
            })
        return Response(data)

    def post(self, request):
        from .models import Agent
        user = Agent.objects.get(id=request.user.id)
        
        # TODO: re-habilitar cuando el sistema de planes esté estable
        # puede, usados, maximo = verificar_limite_plan(user)
        # if not puede:
        #     return Response({
        #         "error": f"Alcanzaste el límite de tu plan ({usados}/{maximo} listados este mes). Actualizá tu plan para continuar.",
        #         "limite_alcanzado": True,
        #         "usados": usados,
        #         "maximo": maximo
        #     }, status=403)
            
        data = request.data
        
        # Permitir tanto JSON plano como objeto anidado 'formData' (React)
        payload = data.get('formData') if isinstance(data, dict) and 'formData' in data else data
        if not isinstance(payload, dict):
            payload = {}
            
        # TODO: re-habilitar cuando el sistema de planes esté estable
        # if not puede_generar(user, 'property'):
        #     return Response({"error": "limite_alcanzado", "mensaje": "Superaste el límite de tu plan. Actualizá tu suscripción."}, status=status.HTTP_403_FORBIDDEN)
        
        titulo = payload.get('titulo') or f"Propiedad en {payload.get('ciudad', 'Desconocida')}"
        tipo_propiedad = payload.get('tipoPropiedad', payload.get('tipo_propiedad', ''))
        ciudad = payload.get('ciudad', '')
        precio = str(payload.get('precio', ''))
        
        # Guardamos en datos el payload limpio
        listado = Listado.objects.create(
            agente=user,
            titulo=titulo,
            tipo_propiedad=tipo_propiedad,
            ciudad=ciudad,
            precio=precio,
            datos=payload
        )
        
        incrementar_uso(user, 'property')
        
        return Response({
            "mensaje": "Listado guardado", 
            "id": listado.id,
            "titulo": listado.titulo
        }, status=status.HTTP_201_CREATED)

class ListadoDetalleView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        try:
            listado = Listado.objects.get(pk=pk, agente=request.user)
            return Response({
                "id": listado.id,
                "titulo": listado.titulo,
                "tipo_propiedad": listado.tipo_propiedad,
                "ciudad": listado.ciudad,
                "precio": listado.precio,
                "video_url": listado.video_url,
                "video_status": listado.video_status,
                "datos": listado.datos
            }, status=status.HTTP_200_OK)
        except Listado.DoesNotExist:
            return Response({"error": "Listado no encontrado"}, status=status.HTTP_404_NOT_FOUND)

    def delete(self, request, pk):
        try:
            listado = Listado.objects.get(pk=pk)
        except Listado.DoesNotExist:
            return Response({"error": "Listado no encontrado"}, status=status.HTTP_404_NOT_FOUND)

        if listado.agente.id != request.user.id:
            return Response({"error": "No tienes permiso para eliminar este listado"}, status=status.HTTP_403_FORBIDDEN)

        # ── Eliminar assets de Cloudinary antes de borrar el registro ─────────
        datos = listado.datos or {}
        public_ids_a_eliminar = []  # [(public_id, resource_type, cloud_name, api_key, api_secret)]

        def _extraer_public_id(obj):
            """Extrae public_id y credenciales de un dict de asset de Cloudinary."""
            if isinstance(obj, dict) and obj.get('public_id'):
                return (
                    obj['public_id'],
                    obj.get('resource_type', 'image'),
                    obj.get('cloudinary_account') or obj.get('cloud_name'),
                    obj.get('api_key'),
                    obj.get('api_secret'),
                )
            return None

        # Portada
        portada = datos.get('portadaUrl') or datos.get('portada_url')
        ref = _extraer_public_id(portada)
        if ref:
            public_ids_a_eliminar.append(ref)

        # Fotos de galería
        for foto in (datos.get('fotosRecorrido') or datos.get('fotos_recorrido') or []):
            ref = _extraer_public_id(foto)
            if ref:
                public_ids_a_eliminar.append(ref)

        # Assets generados en resultados
        resultados = datos.get('resultados') or {}
        for key, val in resultados.items():
            if isinstance(val, dict):
                ref = _extraer_public_id(val)
                if ref:
                    public_ids_a_eliminar.append(ref)
                # Slides de carrusel
                for slide in (val.get('slides') or []):
                    ref = _extraer_public_id(slide)
                    if ref:
                        public_ids_a_eliminar.append(ref)
            elif isinstance(val, list):
                for item in val:
                    ref = _extraer_public_id(item)
                    if ref:
                        public_ids_a_eliminar.append(ref)

        # Eliminar en Cloudinary — fallo individual no interrumpe la operación
        import cloudinary
        import cloudinary.uploader
        from api.services.almacenamiento import AlmacenamientoCloudinary
        from django.conf import settings

        for (pub_id, res_type, cloud_name, api_key_val, api_secret_val) in public_ids_a_eliminar:
            try:
                # Usar credenciales del asset si las tiene, sino la cuenta global
                if cloud_name and api_key_val and api_secret_val:
                    cld_cfg = cloudinary.Config(
                        cloud_name=cloud_name,
                        api_key=api_key_val,
                        api_secret=api_secret_val,
                    )
                    cloudinary.uploader.destroy(pub_id, resource_type=res_type, config=cld_cfg)
                else:
                    cloudinary.uploader.destroy(pub_id, resource_type=res_type)
                logger.info(f"[Eliminar] Asset Cloudinary eliminado: {pub_id}")
            except Exception as cld_err:
                logger.warning(f"[Eliminar] No se pudo eliminar asset {pub_id} de Cloudinary: {cld_err}")

        # ── Borrar el registro de PostgreSQL ──────────────────────────────────
        listado.delete()
        return Response({"mensaje": "Listado eliminado"}, status=status.HTTP_200_OK)


    def put(self, request, pk):
        try:
            listado = Listado.objects.get(pk=pk)
        except Listado.DoesNotExist:
            return Response({"error": "Listado no encontrado"}, status=status.HTTP_404_NOT_FOUND)
            
        if listado.agente.id != request.user.id:
            return Response({"error": "No tienes permiso para modificar este listado"}, status=status.HTTP_403_FORBIDDEN)
            
        data = request.data
        if 'datos' in data:
            listado.datos = data['datos']
        if 'video_url' in data:
            listado.video_url = data['video_url']
        if 'video_status' in data:
            listado.video_status = data['video_status']
        
        listado.save()
        return Response({"mensaje": "Listado actualizado"}, status=status.HTTP_200_OK)


# ---- Celery task + endpoint para generación de video ----
from celery import shared_task
from .services.video_service import generar_video_listado

@shared_task
def generar_video_task(listado_id):
    """Genera video con Remotion para el listado"""
    try:
        success = generar_video_listado(listado_id)
        if success:
            from .models import Listado
            from .plan_utils import registrar_uso
            listado = Listado.objects.get(id=listado_id)
            registrar_uso(listado.agente, 'video')
            return {"status": "completado", "id": listado_id}
        else:
            return {"status": "fallido", "id": listado_id}
    except Exception as e:
        return {"error": str(e)}


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generar_video(request, pk):
    """Dispara la generación de video asincronamente"""
    try:
        listado = Listado.objects.get(id=pk, agente=request.user)
        # Dispara tarea Celery
        generar_video_task.delay(pk)
        return Response({
            "status": "generando",
            "mensaje": "El video se está generando en segundo plano",
            "id": pk
        })
    except Listado.DoesNotExist:
        return Response({"error": "Listado no encontrado"}, status=404)

def construir_contexto_pdf(data, user, request=None):
    # ─── Extraer hint de listado para el almacenamiento ──────────────────────
    listado_id_hint  = data.get('listado_id') or data.get('listadoId')

    # ─── Helpers de imágenes para WeasyPrint ─────────────────────────────
    temp_files = []

    def resolver_imagen(val, tipo='portada', indice=0):
        if not val: return None
        
        if isinstance(val, dict) and 'public_id' in val:
            from api.services.almacenamiento import AlmacenamientoCloudinary
            return AlmacenamientoCloudinary.obtener_url_foto(val)
            
        if isinstance(val, str):
            if val.startswith('http'):
                return val
            if val.startswith('data:'):
                from api.services.almacenamiento import AlmacenamientoCloudinary
                try:
                    res = AlmacenamientoCloudinary.guardar_foto_propiedad(
                        base64_str=val,
                        user_id=user.id,
                        listado_id=listado_id_hint,
                        tipo_foto=tipo,
                        indice=indice
                    )
                    if res and 'public_id' in res:
                        return AlmacenamientoCloudinary.obtener_url_foto(res)
                except Exception as e:
                    logger.error(f"Error subiendo base64 en resolver_imagen: {e}")
                return None
                
        return None



    # ─── Extraer campos normalizados ──────────────────────────────────────
    tipo_propiedad   = data.get('tipoPropiedad', data.get('tipo_propiedad', 'Propiedad'))
    ciudad           = data.get('ciudad', '')
    precio           = str(data.get('precio', ''))
    moneda           = data.get('moneda', 'USD')
    operacion        = data.get('operacion', 'Venta')
    recamaras        = data.get('recamaras', '')
    banos            = data.get('banos', '')
    superficie_cubierta = data.get('superficieCubierta', data.get('superficieConstruida', ''))
    superficie_total = data.get('superficieTotal', data.get('superficieTerreno', ''))
    estacionamientos = data.get('estacionamientos', '')
    amenidades       = data.get('amenidades', [])
    if not isinstance(amenidades, list):
        amenidades = []

    # Datos de agente / agencia
    agente_nombre = data.get('agenteNombre', '') or user.nombre or ''
    agente_email = data.get('agenteEmail', '') or user.email or ''
    agencia_nombre = data.get('agenciaNombre', '') or user.nombre_inmobiliaria or 'LeadBook'
    agente_telefono = data.get('agenteTelefono', '') or user.telefono or ''

    # ─── Procesar imágenes (base64 Y URLs) ───────────────────────────────
    logo_val_raw = data.get('logoAgenciaUrl', data.get('logo_url', ''))
    logo_url = resolver_imagen(logo_val_raw)

    portada_val_raw = data.get('portadaUrl', '')
    fotos_raw = data.get('fotosRecorrido', [])

    fotos_limpias = []
    for f in fotos_raw:
        if isinstance(f, dict):
            if f.get('public_id') and f != logo_val_raw:
                fotos_limpias.append(f)
        elif isinstance(f, str) and f and f != logo_val_raw:
            fotos_limpias.append(f)

    # Si la portada viene vacía o es igual al logo, usar la primera foto real de la propiedad
    if not portada_val_raw or portada_val_raw == logo_val_raw:
        if fotos_limpias:
            portada_val_raw = fotos_limpias[0]

    portada_url = resolver_imagen(portada_val_raw)

    fotos_recorrido_urls = []
    for fv in fotos_limpias:
        url_firma = resolver_imagen(fv)
        if url_firma:
            fotos_recorrido_urls.append(url_firma)

    # ─── Procesar escenas si las hay ─────────────────────────────────────
    escenas = data.get('escenas', [])
    if isinstance(escenas, list):
        escenas_procesadas = []
        for escena in escenas:
            if isinstance(escena, dict) and escena.get('fotoUrl'):
                url_firma = resolver_imagen(escena['fotoUrl'])
                escena = {**escena, 'fotoUrl': url_firma or escena['fotoUrl']}
            escenas_procesadas.append(escena)
        data['escenas'] = escenas_procesadas

    # ─── Descripción IA (si no viene en el payload) ──────────────────────
    descripcion = data.get('descripcion', '')
    if not descripcion:
        amenidades_str = ', '.join(amenidades) if amenidades else 'no especificadas'
        prompt_desc = f"""Generá una descripción inmobiliaria profesional de 2 párrafos para:
{tipo_propiedad} en {operacion} en {ciudad}.
Precio: {moneda} {precio}.
Recámaras: {recamaras}. Baños: {banos}.
Superficie construida: {superficie_cubierta}m2.
Terreno: {superficie_total}m2.
Amenidades: {amenidades_str}.

Párrafo 1: Descripción general de la propiedad y ubicación (3-4 oraciones).
Párrafo 2: Destacar amenidades y estilo de vida que ofrece (3-4 oraciones).
Tono elegante y persuasivo. Solo los 2 párrafos, sin títulos ni bullets."""
        descripcion = smart_call(prompt_desc, system_prompt="Sos un copywriter inmobiliario de lujo. Escribís en español, con tono sofisticado y persuasivo.", agente=user)
        if descripcion:
            from .plan_utils import registrar_uso
            registrar_uso(user, 'ai')
        if not descripcion:
            raise GeminiQuotaExhaustedError("Límite diario de IA alcanzado. Intentá de nuevo mañana.")


    # QR Code del agente
    qr_base64_ = generar_qr_url(
        telefono=agente_telefono,
        tipo_propiedad=tipo_propiedad,
        ciudad=ciudad,
        operacion=operacion,
        precio=precio,
        moneda=moneda
    )

    # ─── Construir contexto del template ─────────────────────────────────
    context = {
        'tipo_propiedad':     tipo_propiedad,
        'ciudad':             ciudad,
        'precio':             precio,
        'moneda':             moneda,
        'operacion':          operacion,
        'recamaras':          recamaras,
        'banos':              banos,
        'superficie_cubierta': superficie_cubierta,
        'superficie_total':   superficie_total,
        'estacionamientos':   estacionamientos,
        'descripcion':        descripcion,
        'amenidades':         amenidades,
        'portada_url':        portada_url or '',
        'fotos_recorrido':    fotos_recorrido_urls,
        'logo_url':           logo_url or '',
        'portada_url_raw':    portada_url or '',
        'fotos_recorrido_raw': fotos_recorrido_urls,
        'logo_url_raw':       logo_url or '',
        'agente_nombre':      agente_nombre,
        'agente_telefono':    agente_telefono,
        'agente_email':       agente_email,
        'agencia_nombre':     agencia_nombre,
        'qr_code':            qr_base64_,
    }


    return context, temp_files, listado_id_hint, tipo_propiedad, ciudad

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generar_pdf(request):
    # TODO: re-habilitar cuando el sistema de planes esté estable
    # if not puede_generar(request.user, 'property'):
    #     return Response({
    #         "error": "limite_alcanzado",
    #         "mensaje": "Superaste el límite de tu plan. Actualizá tu suscripción.",
    #         "upgrade_url": "/precios"
    #     }, status=status.HTTP_403_FORBIDDEN)

    try:
        data = request.data.copy() if hasattr(request.data, 'copy') else dict(request.data)
        
        print(f"[PAYLOAD] portadaUrl tipo: {type(data.get('portadaUrl')).__name__} | valor: {str(data.get('portadaUrl', ''))[:80]}")
        print(f"[PAYLOAD] fotosRecorrido tipo: {type(data.get('fotosRecorrido')).__name__} | largo: {len(data.get('fotosRecorrido', []))}")
        if data.get('fotosRecorrido'):
            primera = data['fotosRecorrido'][0]
            print(f"[PAYLOAD] primera foto tipo: {type(primera).__name__} | valor: {str(primera)[:80]}")

        context, temp_files, listado_id_hint, tipo_propiedad, ciudad = construir_contexto_pdf(data, request.user, request)

        print(f"\n[PDF] Generando para {tipo_propiedad} en {ciudad} | portada: {bool(context.get('portada_url'))} | fotos: {len(context.get('fotos_recorrido', []))} | QR: sí")

        from django.template.loader import render_to_string
        from django.http import HttpResponse
        from api.services.render_engine import render_html_to_pdf
        from api.services.almacenamiento import AlmacenamientoCloudinary
        from api.ai_services import generar_html_gemini, generar_html_desde_template
        from .models import Listado

        context['listado_id'] = listado_id_hint

        try:
            html_string = generar_html_desde_template(context, request.user)
        except Exception as e:
            print(f"[PDF] Error en sistema de templates: {e}. Usando fallback Gemini.")
            html_string = generar_html_gemini(context, request.user)
            
        if not html_string:
            print("[PDF] Fallback: Gemini falló, usando render_to_string estático")
            html_string = render_to_string('pdf/property_brochure_html.html', context)

        # ─── Conversión a PDF Real con Playwright ────────────────────────────
        pdf_url = None
        try:
            print(f"[PDF] Iniciando conversión Playwright para listado {listado_id_hint}...")
            pdf_bytes = render_html_to_pdf(html_string)
            if pdf_bytes:
                print(f"[PDF] Conversión exitosa ({len(pdf_bytes)} bytes). Subiendo a Cloudinary...")
                pdf_url = AlmacenamientoCloudinary.guardar_pdf(
                    pdf_bytes, 
                    user_id=request.user.id, 
                    listado_id=listado_id_hint
                )
                
                # Persistir la URL en el listado para el historial
                if listado_id_hint and pdf_url:
                    try:
                        listado = Listado.objects.get(id=listado_id_hint)
                        if not listado.datos: listado.datos = {}
                        if 'resultados' not in listado.datos: listado.datos['resultados'] = {}
                        
                        # Guardamos ambos para que el frontend tenga fallback
                        listado.datos['resultados']['pdf'] = {
                            "html": html_string,
                            "url": pdf_url
                        }
                        listado.save()
                        print(f"[PDF] URL guardada en DB: {pdf_url}")
                    except Listado.DoesNotExist:
                        pass
            else:
                print("[PDF] Error: Playwright devolvió bytes vacíos.")
        except Exception as pdf_err:
            print(f"[PDF ERROR] Falló la conversión/subida: {pdf_err}")
            # El fallback es seguir adelante con el HTML solo

        # ─── Limpiar archivos temporales de imágenes ─────────────────────────
        for f in temp_files:
            try:
                if os.path.exists(f):
                    os.remove(f)
            except Exception:
                pass

        # Devolvemos JSON para que el frontend maneje el preview y el link de descarga
        return Response({
            "html": html_string,
            "url": pdf_url,
            "listado_id": listado_id_hint
        }, status=status.HTTP_200_OK)

    except GeminiQuotaExhaustedError as e:
        from .models import UserAPIQuota
        quota, _ = UserAPIQuota.objects.get_or_create(
            user=request.user, service='gemini',
            defaults={'daily_limit': 1500, 'monthly_limit': 1500}
        )
        quota.is_blocked = True
        quota.requests_today = quota.daily_limit
        quota.save()
        crear_notificacion(
            request.user,
            'quota_agotada',
            'Alcanzaste el 100% de tu uso de IA',
            'Tus créditos de generación de contenido se agotaron. Se resetean automáticamente a medianoche.'
        )
        return Response({
            "error": "cuota_ia_agotada",
            "mensaje": str(e),
        }, status=status.HTTP_429_TOO_MANY_REQUESTS)

    except Exception as e:
        import traceback
        error_completo = traceback.format_exc()
        print(f"[PDF ERROR COMPLETO]\n{error_completo}")
        return Response({"error": str(e), "trace": error_completo}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generar_imagen_post(request):
    """Genera imagen POST y la sube a Cloudinary"""
    try:
        # TODO: re-habilitar cuando el sistema de planes esté estable
        # if not puede_generar(request.user, 'image'):
        #     return Response({
        #         "error": "limite_alcanzado", 
        #         "mensaje": "Superaste el límite de tu plan. Actualizá tu suscripción.",
        #         "upgrade_url": "/precios"
        #     }, status=status.HTTP_403_FORBIDDEN)

        data = request.data
        
        print(f"[POST DEBUG] agenteNombre: {data.get('agenteNombre')}")
        print(f"[POST DEBUG] agenteTelefono: {data.get('agenteTelefono')}")
        print(f"[POST DEBUG] agenciaNombre: {data.get('agenciaNombre')}")
        print(f"[POST DEBUG] keys recibidas: {list(data.keys())}")

        # Preparar contexto para la plantilla premium
        context = {
            "portada_url": data.get('portadaUrl'),
            "operacion": data.get('operacion', 'Venta'),
            "tipoPropiedad": data.get('tipoPropiedad', 'Propiedad'),
            "ciudad": data.get('ciudad', ''),
            "precio": data.get('precio', ''),
            "moneda": data.get('moneda', 'USD'),
            "titulo": f"{data.get('tipoPropiedad', '')} en {data.get('ciudad', '')}",
            "agente_email": data.get('agenteEmail', '') or data.get('agente_email', ''),
            "logo_url": data.get('logoAgenciaUrl'),
            "caracteristicas": [
                {"label": "m²", "valor": data.get('superficieCubierta') or data.get('superficieTotal')},
                {"label": "Hab", "valor": data.get('recamaras')},
                {"label": "Baños", "valor": data.get('banos')},
            ],
            "agente_nombre": data.get('agenteNombre', ''),
            "agente_telefono": data.get('agenteTelefono', ''),
            "agencia_nombre": data.get('agenciaNombre', '') or data.get('agencia_nombre', ''),
            "qr_url": generar_qr_url(
                telefono=data.get('agenteTelefono', ''),
                tipo_propiedad=data.get('tipoPropiedad', ''),
                ciudad=data.get('ciudad', ''),
                operacion=data.get('operacion', ''),
                precio=data.get('precio', ''),
                moneda=data.get('moneda', '')
            ),
        }
        
        fotos_raw = data.get('fotosRecorrido', [])
        portada_val = fotos_raw[0] if fotos_raw else data.get('portadaUrl', '')
        if isinstance(portada_val, dict) and 'public_id' in portada_val:
            cloud = portada_val.get('cloudinary_account', 'df1vldrhb')
            pid = portada_val.get('public_id', '')
            portada_post = f"https://res.cloudinary.com/{cloud}/image/upload/{pid}"
        else:
            portada_post = str(portada_val) if portada_val else ''
            
        context["portada_url"] = portada_post
        context["caracteristicas"] = [c for c in context["caracteristicas"] if c["valor"]]

        # Renderizar HTML y luego convertir a imagen PNG con Playwright
        TEMPLATES_POST = [
            'renders/post_dubai_night.html',
            'renders/post_beverly_hills.html',
            'renders/post_manhattan.html',
            'renders/post_mediterraneo.html',
            'renders/post_tech_modern.html',
        ]
        template_post = None
        listado_id_val = data.get('listado_id')
        if listado_id_val:
            try:
                from .models import Listado
                listado = Listado.objects.filter(id=listado_id_val).first()
                if listado and listado.datos:
                    template_nombre = listado.datos.get('template', '')
                    if template_nombre:
                        template_post = f'renders/post_{template_nombre}.html'
                        print(f"[POST] Template leído de DB: {template_post}")
            except Exception as e:
                print(f"[POST] Error leyendo template: {e}")

        if not template_post:
            import random
            template_post = random.choice(TEMPLATES_POST)
            print(f"[POST] Template elegido al azar (fallback): {template_post}")
        html_content = render_to_string(template_post, context)
        print(f"[POST] Template elegido: {template_post}")
        image_stream = render_html_to_image(html_content, 1080, 1350)

        # Generar caption con IA (con fallback)
        prompt_text = f"Escribí un caption para Instagram sobre esta propiedad en {data.get('operacion', 'venta')}: {data.get('tipoPropiedad', 'Propiedad')} en {data.get('ciudad', '')} por {data.get('precio', '')}. Máximo 2200 caracteres, usá hashtags y emojis."
        caption = smart_call(prompt_text, system_prompt="Sos un experto en marketing inmobiliario para redes sociales.", agente=request.user)

        # Intentar subir a Cloudinary via Almacenamiento
        try:
            image_stream.seek(0)
            listado_id_val = data.get('listado_id')
            img_url = AlmacenamientoCloudinary.guardar_post(
                image_stream, user_id=request.user.id, listado_id=listado_id_val
            )
            if not img_url:
                raise Exception("Cloudinary no devolvió una URL válida")
            public_id = img_url
        except Exception as cloud_err:
            print(f"[Cloudinary] Error crítico subiendo imagen: {cloud_err}")
            return Response({
                "error": "error_subida",
                "mensaje": "No se pudo subir la imagen a la nube. Reintentá en unos segundos."
            }, status=500)

        # PERSISTENCIA: Guardar en el listado
        if listado_id_val:
            from .models import Listado
            listado_obj = Listado.objects.filter(id=listado_id_val, agente=request.user).first()
            actualizar_resultados_listado(listado_obj, 'post', {"url": img_url, "caption": caption})

        if request.user.is_authenticated:
            incrementar_uso(request.user, 'image')
            from .plan_utils import registrar_uso
            registrar_uso(request.user, 'image')

        return Response({
            "url": img_url,
            "public_id": public_id,
            "caption": caption,
            "texto": caption
        }, status=status.HTTP_200_OK)
    except GeminiQuotaExhaustedError as e:
        from .models import UserAPIQuota
        quota, _ = UserAPIQuota.objects.get_or_create(
            user=request.user, service='gemini',
            defaults={'daily_limit': 1500, 'monthly_limit': 1500}
        )
        quota.is_blocked = True
        quota.requests_today = quota.daily_limit
        quota.save()
        return Response({"error": "cuota_ia_agotada", "mensaje": str(e)}, status=status.HTTP_429_TOO_MANY_REQUESTS)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return Response({"error": str(e), "detalle": traceback.format_exc()}, status=500)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generar_imagen_story(request):
    """Genera imagen Story, la sube a Cloudinary y devuelve también Base64 como respaldo"""
    try:
        # TODO: re-habilitar cuando el sistema de planes esté estable
        # if not puede_generar(request.user, 'image'):
        #     return Response({
        #         "error": "limite_alcanzado",
        #         "mensaje": "Superaste el límite de tu plan. Actualizá tu suscripción.",
        #         "upgrade_url": "/precios"
        #     }, status=status.HTTP_403_FORBIDDEN)

        data = request.data
        
        # Preparar contexto para la plantilla premium
        context = {
            "portada_url": data.get('portadaUrl'),
            "operacion": data.get('operacion', 'Venta'),
            "tipoPropiedad": data.get('tipoPropiedad', 'Propiedad'),
            "ciudad": data.get('ciudad', ''),
            "precio": data.get('precio', ''),
            "moneda": data.get('moneda', 'USD'),
            "logo_url": data.get('logoAgenciaUrl'),
            "caracteristicas": [
                {"label": "m²", "valor": data.get('superficieCubierta') or data.get('superficieTotal')},
                {"label": "Hab", "valor": data.get('recamaras')},
                {"label": "Baños", "valor": data.get('banos')},
            ]
        }
        context["caracteristicas"] = [c for c in context["caracteristicas"] if c["valor"]]

        # Renderizar HTML y luego convertir a imagen PNG con Playwright (Formato vertical 9:16)
        html_content = render_to_string('renders/story.html', context)
        image_stream = render_html_to_image(html_content, 1080, 1920)

        prompt_text = f"Escribí un texto para Instagram Story sobre esta propiedad en {data.get('operacion', 'venta')}: {data.get('tipoPropiedad', 'Propiedad')} en {data.get('ciudad', '')} por {data.get('precio', '')}. Máximo 500 caracteres, enfocado en llamar la atención rápido."
        caption = smart_call(prompt_text, system_prompt="Sos un experto en marketing inmobiliario para redes sociales.", agente=request.user)

        # Intentar subir a Cloudinary via Almacenamiento
        try:
            image_stream.seek(0)
            listado_id_val = data.get('listado_id')
            img_url = AlmacenamientoCloudinary.guardar_story(
                image_stream, user_id=request.user.id, listado_id=listado_id_val
            )
            if not img_url:
                raise Exception("Cloudinary no devolvió una URL válida")
        except Exception as cloud_err:
            print(f"[Cloudinary] Error crítico subiendo story: {cloud_err}")
            return Response({
                "error": "error_subida",
                "mensaje": "No se pudo subir la historia a la nube."
            }, status=500)

        # PERSISTENCIA: Guardar en el listado
        if listado_id_val:
            from .models import Listado
            listado_obj = Listado.objects.filter(id=listado_id_val, agente=request.user).first()
            actualizar_resultados_listado(listado_obj, 'story', {"url": img_url, "caption": caption})

        if request.user.is_authenticated:
            incrementar_uso(request.user, 'image')
            from .plan_utils import registrar_uso
            registrar_uso(request.user, 'image')

        return Response({
            "url": img_url,
            "img_base64": img_base64,
            "public_id": public_id,
            "caption": caption,
            "texto": caption
        }, status=status.HTTP_200_OK)
    except GeminiQuotaExhaustedError as e:
        return Response({"error": "cuota_ia_agotada", "mensaje": str(e)}, status=status.HTTP_429_TOO_MANY_REQUESTS)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return Response({"error": str(e), "detalle": traceback.format_exc()}, status=500)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generar_email(request):
    try:
        # TODO: re-habilitar cuando el sistema de planes esté estable
        # if not puede_generar(request.user, 'ai'):
        #     return Response({
        #         "error": "limite_alcanzado", 
        #         "mensaje": "Superaste el límite de tu plan. Actualizá tu suscripción.",
        #         "upgrade_url": "/precios"
        #     }, status=status.HTTP_403_FORBIDDEN)
            
        data = request.data.copy() if hasattr(request.data, 'copy') else dict(request.data)
        
        prompt_text = f"""
Redacta el cuerpo de un email profesional para ofrecer esta propiedad a un cliente interesado.
Tipo: {data.get('tipoPropiedad', 'Propiedad')}
Ciudad: {data.get('ciudad', '')}
Precio: {data.get('precio', '')}
Operación: {data.get('operacion', 'venta')}
Agente: {data.get('agenteNombre', '')}
Agencia: {data.get('agenciaNombre', '')}

Devuelve **ÚNICAMENTE** y estrictamente un objeto JSON válido (sin Markdown, sin ````json) con la siguiente estructura y nada más:
{{
  "asunto": "el asunto sugerido del correo",
  "html": "el cuerpo del email en una línea, todo en codigo html inline, usando etiquetas como <br>, <strong> (sin los tags <html>, <head> o <body>, solo contenido directo)",
  "texto_plano": "el equivalente en texto plano básico pero atractivo"
}}
"""
        json_str = smart_call(prompt_text, system_prompt="Sos un asistente técnico que solo responde en JSON.", agente=request.user)
        
        if json_str is None:
            json_str = '{"asunto": "Propiedad destacada", "html": "<div>Tenemos una excelente oportunidad para vos. Contestá a este mail para más detalles.</div>", "texto_plano": "Tenemos una excelente oportunidad para vos. Contestá a este mail para más detalles."}'
            
        import json
        try:
            parsed = json.loads(json_str)
        except:
            if '```json' in json_str:
                json_str = json_str.split('```json')[1].split('```')[0].strip()
                parsed = json.loads(json_str)
            else:
                parsed = {
                    "asunto": "Propiedad destacada",
                    "html": "<div>Propiedad disponible</div>",
                    "texto_plano": "Propiedad disponible"
                }
                
        if request.user.is_authenticated:
            incrementar_uso(request.user, 'ai')

        # Inyectar en plantilla premium para que no sea solo texto pelado
        context = {
            "asunto": parsed.get("asunto", "Propiedad destacada"),
            "tipoPropiedad": data.get('tipoPropiedad', 'Propiedad'),
            "ciudad": data.get('ciudad', ''),
            "precio": data.get('precio', ''),
            "moneda": data.get('moneda', 'USD'),
            "operacion": data.get('operacion', 'Venta'),
            "agenteNombre": data.get('agenteNombre', request.user.first_name if request.user.first_name else request.user.username),
            "agenciaNombre": data.get('agenciaNombre', ''),
            "portada_url": data.get('portadaUrl'),
            "logo_url": data.get('logoAgenciaUrl'),
            "html_content": parsed.get("html", "")
        }
        premium_html = render_to_string('emails/marketing.html', context)
        parsed["html"] = premium_html
        
        # PERSISTENCIA: Guardar en el listado
        listado_id_val = data.get('listado_id') or data.get('listadoId')
        if listado_id_val:
            from .models import Listado
            listado_obj = Listado.objects.filter(id=listado_id_val, agente=request.user).first()
            actualizar_resultados_listado(listado_obj, 'email', parsed)
            
        return Response(parsed, status=status.HTTP_200_OK)
    except GeminiQuotaExhaustedError as e:
        return Response({"error": "cuota_ia_agotada", "mensaje": str(e)}, status=status.HTTP_429_TOO_MANY_REQUESTS)
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@permission_classes([AllowAny])
def serve_pdf_file(request, uuid_str):
    """Sirve el PDF generado. Soporta ambos prefijos (lb_pdf_ y pdf_) para compatibilidad."""
    from django.http import FileResponse
    # Buscar con nuevo prefijo primero, luego el legacy
    for prefix in ['lb_pdf_', 'pdf_']:
        pdf_path = os.path.join(tempfile.gettempdir(), f"{prefix}{uuid_str}.pdf")
        if os.path.exists(pdf_path):
            response = FileResponse(open(pdf_path, 'rb'), content_type='application/pdf')
            response['Content-Disposition'] = 'inline; filename="ficha-leadbook.pdf"'
            response['X-Frame-Options'] = 'ALLOWALL'
            response['Access-Control-Allow-Origin'] = '*'
            response['Content-Security-Policy'] = "frame-ancestors *"
            return response
    return Response({"error": "PDF no encontrado"}, status=status.HTTP_404_NOT_FOUND)

import mercadopago
from decouple import config
from datetime import datetime, timedelta

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def mp_checkout(request):
    plan = request.data.get('plan')
    ciclo = request.data.get('ciclo', 'monthly')
    
    planes = {
        'starter': {'nombre': 'LeadBook Starter', 'precio_mensual': 70000, 'precio_anual': 52500},
        'pro': {'nombre': 'LeadBook Pro', 'precio_mensual': 161000, 'precio_anual': 120750},
        'scale': {'nombre': 'LeadBook Scale', 'precio_mensual': 270000, 'precio_anual': 202500},
        'business': {'nombre': 'LeadBook Business', 'precio_mensual': 542000, 'precio_anual': 406500},
    }
    
    if plan not in planes:
        return Response({"error": "Plan inválido"}, status=400)
    
    plan_data = planes[plan]
    precio = plan_data['precio_anual'] if ciclo == 'annual' else plan_data['precio_mensual']
    nombre = f"{plan_data['nombre']} ({'Anual' if ciclo == 'annual' else 'Mensual'})"
    
    sdk = mercadopago.SDK(config('MP_ACCESS_TOKEN'))
    frontend_url = config('FRONTEND_URL', default='https://front-saas-production-1e0c.up.railway.app')
    
    preference_data = {
        "items": [{
            "id": f"{plan}_{ciclo}",
            "title": nombre,
            "quantity": 1,
            "currency_id": "ARS",
            "unit_price": float(precio)
        }],
        "payer": {"email": request.user.email},
        "back_urls": {
            "success": f"{frontend_url}/pago-exitoso?plan={plan}",
            "failure": f"{frontend_url}/pago-fallido",
            "pending": f"{frontend_url}/pago-pendiente"
        },
        "auto_return": "approved",
        "external_reference": f"{request.user.id}|{plan}",
    }
    
    preference_response = sdk.preference().create(preference_data)
    
    if preference_response["status"] == 201:
        return Response({
            "init_point": preference_response["response"]["init_point"],
            "preference_id": preference_response["response"]["id"]
        })
    else:
        print(f"MP Error: {preference_response}")
        return Response({"error": "Error al crear preferencia de pago"}, status=500)



@api_view(['POST'])
@permission_classes([IsAuthenticated])
def mp_checkout_api_extra(request):
    """Genera link de pago para comprar una API adicional de Gemini"""
    servicio = request.data.get('servicio', 'gemini')
    
    PRECIOS_EXTRA = {
        'gemini':       {'nombre': 'Contenido IA — Adicional (+1500 créditos)',     'precio': 1},
        'elevenlabs':   {'nombre': 'Voces Neurales — Adicional (+10.000 caracteres)', 'precio': 1},
        'uploadpost':   {'nombre': 'Gestor de Redes — Adicional (+10 publicaciones)', 'precio': 1},
        'pack_completo':{'nombre': 'Pack Completo — Todos los recursos',              'precio': 1},
    }
    
    if servicio not in PRECIOS_EXTRA:
        return Response({"error": "Servicio inválido"}, status=400)
    
    item = PRECIOS_EXTRA[servicio]
    sdk = mercadopago.SDK(config('MP_ACCESS_TOKEN'))
    frontend_url = config('FRONTEND_URL', default='https://front-saas-production-1e0c.up.railway.app')
    
    preference_data = {
        "items": [{
            "id": f"extra_{servicio}",
            "title": item['nombre'],
            "description": f"Uso adicional permanente mensual de {item['nombre']}. Se suma a tu límite actual.",
            "quantity": 1,
            "currency_id": "ARS",
            "unit_price": float(item['precio'])
        }],
        "payer": {"email": request.user.email},
        "back_urls": {
            "success": f"{frontend_url}/dashboard?extra=exitoso&servicio={servicio}",
            "failure": f"{frontend_url}/precios?extra=fallido",
            "pending": f"{frontend_url}/dashboard?extra=pendiente"
        },
        "auto_return": "approved",
        "external_reference": f"{request.user.id}|extra_{servicio}",
    }
    
    preference_response = sdk.preference().create(preference_data)
    
    if preference_response["status"] == 201:
        return Response({
            "init_point": preference_response["response"]["init_point"],
            "preference_id": preference_response["response"]["id"]
        })
    else:
        return Response({"error": "Error al crear preferencia de pago"}, status=500)



@api_view(['POST'])
@permission_classes([AllowAny])
def mp_webhook(request):
    topic = request.data.get('type')
    data_id = request.data.get('data', {}).get('id')
    
    if not data_id:
        return Response({"status": "ok"})
    
    try:
        import requests as req
        headers = {"Authorization": f"Bearer {config('MP_ACCESS_TOKEN')}"}
        
        if topic == 'payment':
            response = req.get(
                f"https://api.mercadopago.com/v1/payments/{data_id}",
                headers=headers
            )
        elif topic == 'subscription_preapproval':
            response = req.get(
                f"https://api.mercadopago.com/preapproval/{data_id}",
                headers=headers
            )
        else:
            return Response({"status": "ok"})
        
        data = response.json()
        status = data.get("status")
        external_ref = data.get("external_reference", "")
        
        if status in ["approved", "authorized"] and "|" in external_ref:
            user_id, tipo = external_ref.split("|", 1)
            from .models import Agent
            try:
                agent = Agent.objects.get(id=int(user_id))
                if tipo.startswith('extra_'):
                    # Compra de API adicional
                    if tipo == 'extra_pack_completo':
                        for svc in ['gemini', 'elevenlabs', 'uploadpost']:
                            keys_ya_usadas = BundleAPIExtra.objects.filter(
                                usuario=agent, servicio=svc, activa=True
                            ).values_list('api_key_id', flat=True)
                            key_disponible = APIKey.objects.filter(
                                servicio=svc, status__in=['available', 'active']
                            ).exclude(id__in=keys_ya_usadas).first()
                            if key_disponible:
                                BundleAPIExtra.objects.create(
                                    usuario=agent, api_key=key_disponible,
                                    servicio=svc, activa=True, pago_id=str(data_id)
                                )
                                from .models import UserAPIQuota
                                quota, _ = UserAPIQuota.objects.get_or_create(user=agent, service=svc)
                                quota.is_blocked = False
                                # Incrementos específicos por servicio
                                inc = 1500 if svc == 'gemini' else 10000 if svc == 'elevenlabs' else 10
                                quota.monthly_limit = (quota.monthly_limit or (1500 if svc=='gemini' else 10000 if svc=='elevenlabs' else 10)) + inc
                                quota.daily_limit = (quota.daily_limit or (1500 if svc=='gemini' else 10000 if svc=='elevenlabs' else 10)) + inc
                                quota.save()
                        print(f"[MP] Pack completo asignado: user {user_id}")
                    else:
                        servicio = tipo.replace('extra_', '')
                        from .models import APIKey, BundleAPIExtra
                        # Buscar una APIKey disponible del servicio que no esté asignada como extra
                        keys_ya_usadas = BundleAPIExtra.objects.filter(
                            usuario=agent, servicio=servicio, activa=True
                        ).values_list('api_key_id', flat=True)
                        key_disponible = APIKey.objects.filter(
                            servicio=servicio,
                            status__in=['available', 'active']
                        ).exclude(id__in=keys_ya_usadas).first()
                        
                        if key_disponible:
                            BundleAPIExtra.objects.create(
                                usuario=agent, api_key=key_disponible,
                                servicio=servicio, activa=True, pago_id=str(data_id)
                            )
                            # Actualizar el límite en UserAPIQuota
                            from .models import UserAPIQuota
                            quota, _ = UserAPIQuota.objects.get_or_create(user=agent, service=servicio)
                            quota.is_blocked = False
                            # Aumentar límites (mensual y diario)
                            inc = 1500 if servicio == 'gemini' else 10000 if servicio == 'elevenlabs' else 10
                            quota.monthly_limit = (quota.monthly_limit or inc) + inc
                            quota.daily_limit = (quota.daily_limit or inc) + inc
                            quota.save()
                            print(f"[MP] API extra asignada: user {user_id} → {servicio} extra")
                        else:
                            print(f"[MP] No hay APIKey disponible para {servicio}")
                else:
                    # Compra de plan normal
                    agent.plan_nombre = tipo
                    agent.plan_activo = True
                    agent.save()
                    print(f"[MP] Plan actualizado: user {user_id} → {tipo}")



            except Agent.DoesNotExist:
                print(f"[MP] Usuario no encontrado: {user_id}")
    except Exception as e:
        print(f"[MP] Error webhook: {e}")
    
    return Response({"status": "ok"})

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def plan_status(request):
    user = request.user
    return Response({
        "plan_nombre": user.plan_nombre,
        "plan_activo": user.plan_activo,
        "plan_seleccionado": user.plan_seleccionado,
    })

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def seleccionar_plan_free(request):
    user = request.user
    user.plan_nombre = 'free'
    user.plan_activo = True
    user.plan_seleccionado = True
    user.save()
    return Response({"ok": True, "plan": "free"})

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_plan_info_mp(request):
    from .plan_utils import LIMITES
    from .models import UsageLog
    agent = request.user
    plan = agent.plan_nombre or 'free'
    limites = LIMITES.get(plan, LIMITES['free'])
    now = timezone.now()
    ai_used = UsageLog.objects.filter(
        agent=agent, tipo='ai',
        fecha__year=now.year, fecha__month=now.month
    ).count()
    images_used = UsageLog.objects.filter(
        agent=agent, tipo='image',
        fecha__year=now.year, fecha__month=now.month
    ).count()
    videos_used = UsageLog.objects.filter(
        agent=agent, tipo='video',
        fecha__year=now.year, fecha__month=now.month
    ).count()
    listados_mes = Listado.objects.filter(
        agente=agent,
        creado_en__year=now.year, creado_en__month=now.month
    ).count()
    return Response({
        "plan_nombre": plan,
        "mp_public_key": settings.MP_PUBLIC_KEY,
        "uso_actual": {
            "properties_used": listados_mes,
            "ai_used": ai_used,
            "images_used": images_used,
            "videos_used": videos_used
        },
        "limites": {
            "properties_per_month": limites['properties'],
            "ai_generations": limites['ai'],
            "image_generations": limites['images'],
            "video_generations": limites['videos']
        }
    })


import secrets
import hashlib
from django.core.mail import send_mail
from datetime import timedelta


@api_view(['POST'])
@permission_classes([AllowAny])
def send_otp(request):
    email = request.data.get('email', '').strip().lower()
    if not email:
        return Response({"error": "Email requerido"}, status=400)

    recent = OTPCode.objects.filter(
        email=email,
        created_at__gte=timezone.now() - timedelta(minutes=15)
    ).count()
    if recent >= 3:
        return Response({"error": "Demasiados intentos. Esperá 15 minutos."}, status=429)

    code = str(secrets.randbelow(900000) + 100000)
    code_hash = hashlib.sha256(code.encode()).hexdigest()
    expires_at = timezone.now() + timedelta(minutes=10)

    OTPCode.objects.create(
        email=email,
        code_hash=code_hash,
        expires_at=expires_at
    )

    # Envío del OTP robusto: intenta Celery asíncrono; si falla o no hay broker,
    # cae a envío síncrono en el request. Así funciona en Railway sin worker.
    import sys
    from django.conf import settings

    # Log de diagnóstico MUY visible en Railway
    print(f"[EMAIL] Intentando enviar a {email}", flush=True)
    print(
        f"[EMAIL] DIAG backend={settings.EMAIL_BACKEND} "
        f"host={settings.EMAIL_HOST}:{settings.EMAIL_PORT} "
        f"user_set={bool(settings.EMAIL_HOST_USER)} "
        f"pass_set={bool(settings.EMAIL_HOST_PASSWORD)} "
        f"eager={getattr(settings, 'CELERY_TASK_ALWAYS_EAGER', True)}",
        flush=True,
    )
    sys.stdout.flush()

    sent_mode = None
    try:
        from .tasks import send_otp_email_async

        if getattr(settings, 'CELERY_TASK_ALWAYS_EAGER', True):
            # Eager: ejecutar la task sincronamente sin broker
            send_otp_email_async(email, code)
            sent_mode = 'sync-eager'
        else:
            # Intentar enviar al broker Celery (Redis)
            send_otp_email_async.delay(email, code)
            sent_mode = 'celery-queued'
        print(f"[EMAIL] Enviado correctamente a {email} (mode={sent_mode})", flush=True)
    except Exception as e_celery:
        # Broker caído, sin Redis, o cualquier otro problema: fallback sync
        print(f"[EMAIL] ERROR al enviar (celery path): {type(e_celery).__name__}: {str(e_celery)}", flush=True)
        print(f"[EMAIL] Intentando fallback sync a {email}", flush=True)
        try:
            from .tasks import send_otp_email_async as _send_sync
            _send_sync(email, code)
            sent_mode = 'sync-fallback'
            print(f"[EMAIL] Enviado correctamente a {email} (mode={sent_mode})", flush=True)
        except Exception as e_sync:
            print(f"[EMAIL] ERROR al enviar: {str(e_sync)}", flush=True)
            import traceback
            traceback.print_exc()
            sent_mode = f'error:{type(e_sync).__name__}'

    sys.stdout.flush()
    return Response({"mensaje": "Código enviado", "email": email, "_mode": sent_mode})


@api_view(['POST'])
@permission_classes([AllowAny])
def verify_otp(request):
    email = request.data.get('email', '').strip().lower()
    code = request.data.get('code', '').strip()

    if not email or not code:
        return Response({"error": "Email y código requeridos"}, status=400)

    otp = OTPCode.objects.filter(
        email=email,
        verified=False
    ).order_by('-created_at').first()

    if not otp:
        return Response({"error": "Código inválido o ya utilizado"}, status=400)

    if otp.is_expired():
        return Response({"error": "Código expirado. Pedí uno nuevo."}, status=400)

    if otp.attempts >= 5:
        return Response({"error": "Demasiados intentos. Pedí un nuevo código."}, status=429)

    # Verificar hash ANTES de incrementar attempts para no penalizar el intento correcto
    code_hash = OTPCode.hash_code(code)
    if otp.code_hash != code_hash:
        otp.attempts += 1
        otp.save()
        intentos_restantes = 5 - otp.attempts
        return Response({"error": f"Código incorrecto. {intentos_restantes} intentos restantes."}, status=400)

    # Código correcto
    otp.verified = True
    otp.save()

    return Response({"verificado": True, "email": email})


@api_view(['POST'])
@permission_classes([AllowAny])
def recuperar_password(request):
    from .models import Agent
    email = request.data.get('email', '').strip().lower()
    if not email:
        return Response({"error": "Email requerido"}, status=400)
    
    user = Agent.objects.filter(email=email).first()
    if not user:
        return Response({"error": "No encontramos una cuenta con ese email"}, status=404)
    
    import secrets
    import hashlib
    from datetime import timedelta
    from django.utils import timezone
    
    code = str(secrets.randbelow(900000) + 100000)
    code_hash = hashlib.sha256(code.encode()).hexdigest()
    expires_at = timezone.now() + timedelta(minutes=10)
    
    OTPCode.objects.create(
        email=email,
        code_hash=code_hash,
        expires_at=expires_at,
        tipo="recuperacion"
    )

    # Envío robusto con fallback síncrono (idéntico a send_otp)
    try:
        from django.conf import settings
        from .tasks import send_otp_email_async
        if getattr(settings, 'CELERY_TASK_ALWAYS_EAGER', True):
            send_otp_email_async(email, code)
        else:
            send_otp_email_async.delay(email, code)
    except Exception as e_celery:
        print(f"[OTP-RECOV] Celery falló ({e_celery}). Fallback sync.")
        try:
            from .tasks import send_otp_email_async as _send_sync
            _send_sync(email, code)
        except Exception as e_sync:
            print(f"[OTP-RECOV] ERROR envío síncrono: {e_sync}")

    return Response({"mensaje": "Código enviado", "email": email}, status=200)


@api_view(['POST'])
@permission_classes([AllowAny])
def confirmar_recuperacion(request):
    from .models import Agent
    email = request.data.get('email', '').strip().lower()
    code = request.data.get('codigo', '').strip()
    nueva_password = request.data.get('nueva_password', '')
    
    if not email or not code or not nueva_password:
        return Response({"error": "Faltan datos requeridos"}, status=400)
    
    otp = OTPCode.objects.filter(
        email=email,
        tipo="recuperacion",
        verified=False
    ).order_by('-created_at').first()
    
    if not otp:
        return Response({"error": "Código inválido"}, status=400)
    if otp.is_expired():
        return Response({"error": "Código expirado"}, status=400)
    if not otp.is_valid(code):
        return Response({"error": "Código incorrecto"}, status=400)
    
    user = Agent.objects.filter(email=email).first()
    if not user:
        return Response({"error": "Usuario no encontrado"}, status=404)
    
    user.set_password(nueva_password)
    user.save()
    
    otp.verified = True
    otp.save()
    
    return Response({"mensaje": "Contraseña actualizada correctamente"}, status=200)


@api_view(['GET'])
@permission_classes([AllowAny])
def obtener_terminos(request):
    """Devuelve los Términos y Condiciones vigentes"""
    try:
        terminos = TerminosCondiciones.objects.filter(activo=True).latest('fecha_actualizacion')
        serializer = TerminosCondicionesSerializer(terminos)
        return Response(serializer.data)
    except TerminosCondiciones.DoesNotExist:
        return Response({"error": "Términos no disponibles"}, status=404)

@api_view(['GET'])
@permission_classes([AllowAny])
def obtener_politica_privacidad(request):
    """Devuelve la Política de Privacidad vigente"""
    try:
        politica = PoliticaPrivacidad.objects.filter(activo=True).latest('fecha_actualizacion')
        serializer = PoliticaPrivacidadSerializer(politica)
        return Response(serializer.data)
    except PoliticaPrivacidad.DoesNotExist:
        return Response({"error": "Política de privacidad no disponible"}, status=404)

@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def amenidades_presets(request):
    from .models import AmenidadPreset
    agente = request.user
    if request.method == 'GET':
        presets = AmenidadPreset.objects.filter(agente=agente)
        return Response({'presets': [p.nombre for p in presets]})
    
    if request.method == 'POST':
        nombre = request.data.get('nombre', '').strip()
        if not nombre:
            return Response({'error': 'Nombre requerido'}, status=400)
        preset, created = AmenidadPreset.objects.get_or_create(
            agente=agente, nombre=nombre
        )
        return Response({
            'nombre': preset.nombre, 
            'created': created
        }, status=201 if created else 200)

from django.utils import timezone
from datetime import timedelta

ADMIN_KEY = config('ADMIN_KEY', default='')

def check_admin(request):
    return request.headers.get('X-Admin-Key') == ADMIN_KEY

@api_view(['GET'])
@permission_classes([AllowAny])
def admin_stats(request):
    """
    Dashboard de administración: Métricas globales y estado detallado de las APIs asignadas.
    """
    if not check_admin(request):
        return Response({"error": "Forbidden"}, status=403)
    
    from .models import Agent, APIKey, UserAPIQuota, APIBundleAssignment
    from django.utils import timezone
    from datetime import timedelta

    ahora = timezone.now()
    hoy = ahora - timedelta(hours=24)
    semana = ahora - timedelta(days=7)
    
    from .models import Agent, Listado
    
    total = Agent.objects.count()
    activos_hoy = Agent.objects.filter(
        last_login__gte=hoy).count()
    activos_semana = Agent.objects.filter(
        last_login__gte=semana).count()
    nuevos_hoy = Agent.objects.filter(
        fecha_registro__gte=hoy).count()
    nuevos_semana = Agent.objects.filter(
        fecha_registro__gte=semana).count()
    
    distribucion = {}
    for plan in ['free','starter','pro','scale','business']:
        distribucion[plan] = Agent.objects.filter(
            plan_nombre=plan).count()
    
    try:
        total_listados = Listado.objects.count()
    except:
        total_listados = 0
    
    return Response({
        "total_usuarios": total,
        "activos_hoy": activos_hoy,
        "activos_semana": activos_semana,
        "nuevos_hoy": nuevos_hoy,
        "nuevos_semana": nuevos_semana,
        "distribucion_planes": distribucion,
        "total_listados": total_listados
    })

@api_view(['GET'])
@permission_classes([AllowAny])
def admin_usuarios(request):
    if not check_admin(request):
        return Response({"error": "Forbidden"}, status=403)
    try:
        from .models import Agent, Listado
        incluir_eliminados = request.query_params.get('incluir_eliminados') in ('1', 'true', 'True')
        agentes_qs = Agent.objects.all().order_by('-fecha_registro')
        if not incluir_eliminados:
            try:
                agentes_qs = agentes_qs.filter(eliminado_en__isnull=True)
            except Exception as e:
                import sys
                print(f"[admin_usuarios] WARN filter eliminado_en fallo: {e}", file=sys.stderr, flush=True)
        
        resultado = []
        for a in agentes_qs:
            try:
                listados = Listado.objects.filter(agente=a).count()
            except:
                listados = 0
            
            resultado.append({
                "id": a.id,
                "email": a.email,
                "nombre": getattr(a, 'nombre', ''),
                "agencia": getattr(a, 'agencia', '') or getattr(a, 'nombre_inmobiliaria', ''),
                "plan_nombre": getattr(a, 'plan_nombre', 'free'),
                "plan_activo": getattr(a, 'plan_activo', True),
                "fecha_registro": a.fecha_registro.strftime('%Y-%m-%d %H:%M') if a.fecha_registro else '',
                "last_login": a.last_login.strftime('%Y-%m-%d %H:%M') if a.last_login else 'Nunca',
                "listados_count": listados,
                "pais": getattr(a, 'pais', ''),
                "nicho": getattr(a, 'nicho', ''),
            })
        return Response({"usuarios": resultado})
    except Exception as e:
        import traceback, sys
        traceback.print_exc(file=sys.stderr)
        sys.stderr.flush()
        return Response({"error": "internal", "detail": str(e)[:300]}, status=500)

@api_view(['DELETE'])
@permission_classes([AllowAny])
def admin_eliminar_usuario(request, user_id):
    if not check_admin(request):
        return Response({"error": "Forbidden"}, status=403)
    
    from .models import Agent
    try:
        agent = Agent.objects.get(id=user_id)
        agent.delete()
        return Response({"mensaje": "Usuario eliminado"})
    except Agent.DoesNotExist:
        return Response({"error": "No encontrado"}, status=404)

@api_view(['POST'])
@permission_classes([AllowAny])
def admin_cambiar_plan(request, user_id):
    if not check_admin(request):
        return Response({"error": "Forbidden"}, status=403)
    
    nuevo_plan = request.data.get('plan')
    planes_validos = ['free','starter','pro','scale','business']
    
    if nuevo_plan not in planes_validos:
        return Response({"error": "Plan inválido"}, status=400)
    
    from .models import Agent
    try:
        agent = Agent.objects.get(id=user_id)
        agent.plan_nombre = nuevo_plan
        agent.save()
        return Response({
            "mensaje": f"Plan actualizado a {nuevo_plan}",
            "plan": nuevo_plan
        })
    except Agent.DoesNotExist:
        return Response({"error": "No encontrado"}, status=404)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def dashboard(request):
    agent = request.user
    now = timezone.now()
    start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    from .models import Listado, UsageLog
    from .plan_utils import LIMITES

    listados = Listado.objects.filter(agente=agent)
    listados_este_mes = listados.filter(creado_en__gte=start_of_month).count()
    total_generados = listados.count()
    videos_creados = listados.aggregate(total=Sum('videos_creados'))['total'] or 0

    listados_recientes = list(listados.order_by('-creado_en')[:5].values(
        'id', 'titulo', 'tipo_propiedad', 'ciudad', 'precio', 'creado_en'
    ))

    plan = agent.plan_nombre or 'free'
    limites = LIMITES.get(plan, LIMITES['free'])

    # Uso actual del mes (via UsageLog)
    ai_used = UsageLog.objects.filter(
        agent=agent, tipo='ai',
        fecha__year=now.year, fecha__month=now.month
    ).count()
    images_used = UsageLog.objects.filter(
        agent=agent, tipo='image',
        fecha__year=now.year, fecha__month=now.month
    ).count()
    videos_used = UsageLog.objects.filter(
        agent=agent, tipo='video',
        fecha__year=now.year, fecha__month=now.month
    ).count()

    return Response({
        'nombre_inmobiliaria': getattr(agent, 'nombre_inmobiliaria', None),
        'logo_url': getattr(agent, 'logo_url', None),
        'listados_este_mes': listados_este_mes,
        'total_generados': total_generados,
        'videos_creados': videos_creados,
        'conexiones_activas': 0,
        'listados_recientes': listados_recientes,
        'plan': plan,
        'plan_limites': {
            'properties_per_month': limites['properties'],
            'ai_generations': limites['ai'],
            'image_generations': limites['images'],
            'video_generations': limites['videos'],
            'branding': plan not in ('free',),
        },
        'uso_actual': {
            'properties_used': listados_este_mes,
            'ai_used': ai_used,
            'images_used': images_used,
            'videos_used': videos_used,
        }
    })

@api_view(['GET'])
@permission_classes([AllowAny])
def admin_listados(request):
    """Todos los listados del sistema"""
    if not check_admin(request):
        return Response({"error": "Forbidden"}, status=403)
    from .models import Listado
    listados = Listado.objects.select_related('agente').order_by('-creado_en')[:100]
    data = [{
        "id": l.id,
        "titulo": l.titulo,
        "tipo": l.tipo_propiedad,
        "ciudad": l.ciudad,
        "precio": str(l.precio) if l.precio else None,
        "agente_email": l.agente.email,
        "agente_nombre": l.agente.nombre,
        "video_status": l.video_status,
        "creado_en": l.creado_en.strftime('%Y-%m-%d %H:%M') if l.creado_en else ''
    } for l in listados]
    return Response({"listados": data, "total": len(data)})

@api_view(['GET'])
@permission_classes([AllowAny])
def admin_assets(request):
    """Stats de assets generados"""
    if not check_admin(request):
        return Response({"error": "Forbidden"}, status=403)
    from .models import GeneratedAsset
    total = GeneratedAsset.objects.count()
    por_tipo = {}
    for tipo in ['PDF', 'VIDEO', 'EMAIL', 'SOCIAL']:
        por_tipo[tipo] = GeneratedAsset.objects.filter(asset_type=tipo).count()
    por_status = {}
    for status in ['PENDING', 'PROCESSING', 'COMPLETED', 'FAILED']:
        por_status[status] = GeneratedAsset.objects.filter(status=status).count()
    return Response({
        "total": total,
        "por_tipo": por_tipo,
        "por_status": por_status
    })

@api_view(['GET'])
@permission_classes([AllowAny])
def admin_pagos(request):
    """Historial de pagos/planes"""
    if not check_admin(request):
        return Response({"error": "Forbidden"}, status=403)
    from .models import Agent
    agentes_pagos = Agent.objects.exclude(
        plan_nombre='free'
    ).order_by('-fecha_registro')
    data = [{
        "email": a.email,
        "nombre": a.nombre,
        "plan": a.plan_nombre,
        "plan_activo": a.plan_activo,
        "mp_customer_id": a.mp_customer_id or '',
        "mp_subscription_id": a.mp_subscription_id or '',
        "fecha_registro": a.fecha_registro.strftime('%Y-%m-%d') if a.fecha_registro else ''
    } for a in agentes_pagos]
    return Response({"pagos": data, "total_pagos": len(data)})

@api_view(['GET'])
@permission_classes([AllowAny])
def admin_usuario_detalle(request, user_id):
    """Detalle completo de un usuario"""
    if not check_admin(request):
        return Response({"error": "Forbidden"}, status=403)
    from .models import Agent, Listado
    try:
        a = Agent.objects.get(id=user_id)
    except Agent.DoesNotExist:
        return Response({"error": "Usuario no encontrado"}, status=404)
    listados = Listado.objects.filter(agente=a).order_by('-creado_en')
    return Response({
        "id": a.id,
        "email": a.email,
        "nombre": a.nombre,
        "agencia": a.agencia or '',
        "telefono": a.telefono or '',
        "pais": a.pais or '',
        "nicho": a.nicho or '',
        "plan": a.plan_nombre,
        "plan_activo": a.plan_activo,
        "is_active": a.is_active,
        "fecha_registro": a.fecha_registro.strftime('%Y-%m-%d %H:%M') if a.fecha_registro else '',
        "last_login": a.last_login.strftime('%Y-%m-%d %H:%M') if a.last_login else 'Nunca',
        "total_listados": listados.count(),
        "listados_recientes": [{
            "titulo": l.titulo,
            "tipo": l.tipo_propiedad,
            "ciudad": l.ciudad,
            "creado_en": l.creado_en.strftime('%Y-%m-%d') if l.creado_en else ''
        } for l in listados[:10]]
    })


@api_view(['GET', 'POST'])
@permission_classes([AllowAny])
def admin_suspender_usuario(request, user_id):
    """Suspender o reactivar un usuario"""
    if not check_admin(request):
        return Response({"error": "Forbidden"}, status=403)
    if request.method != 'POST':
        return Response({"error": "Method not allowed"}, status=405)
    from .models import Agent
    try:
        a = Agent.objects.get(id=user_id)
    except Agent.DoesNotExist:
        return Response({"error": "Usuario no encontrado"}, status=404)
    a.is_active = not a.is_active
    a.save()
    estado = "suspendido" if not a.is_active else "reactivado"
    return Response({"ok": True, "estado": estado, "is_active": a.is_active})

import requests as http_requests

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def conexiones_init(request):
    """
    Crea perfil en UploadPost para el usuario y devuelve 
    la URL segura para conectar sus redes sociales.
    """
    import traceback, sys
    try:
        from django.conf import settings
        from api.pool_manager import get_api_key
        import os
        
        user = request.user
        username = f"leadbook_{user.id}"
        print(f"[conexiones_init] user={user.email} username={username}", flush=True)
        
        # 1. Key del bundle/pool del usuario
        api_key = get_api_key(user, 'uploadpost')
        
        # 2. Fallback: key global del .env de producción
        if not api_key:
            api_key = (
                getattr(settings, 'UPLOADPOST_API_KEY', '') or
                os.environ.get('UPLOADPOST_API_KEY', '') or
                os.environ.get('UPLOAD_POST_API_KEY', '')
            ) or None
            if api_key:
                print(f"[conexiones_init] Usando UPLOADPOST_API_KEY global para {user.email}", flush=True)
        
        if not api_key:
            print(f"[conexiones_init] Sin key uploadpost para {user.email}. Plan={getattr(user, 'plan_nombre', 'free')}", flush=True)
            return Response({
                "success": False,
                "error": "Tu cuenta no tiene una API de publicación asignada. Contactá a soporte."
            }, status=400)
        
        headers = {
            "Authorization": f"Apikey {api_key}",
            "Content-Type": "application/json"
        }
        
        # PASO 1: Crear perfil (si no existe)
        create_resp = http_requests.post(
            "https://api.upload-post.com/api/uploadposts/users",
            headers=headers,
            json={"username": username},
            timeout=10
        )
        print(f"[conexiones_init] create_profile status={create_resp.status_code}", flush=True)
        # 200 o 409 (ya existe) son aceptables
        if create_resp.status_code not in [200, 201, 409]:
            err_text = create_resp.text[:200]
            if "PROFILE_LIMIT_REACHED" in err_text or "limit of 2 profiles" in err_text:
                return Response({
                    "success": False,
                    "error": "Alcanzaste el límite de cuentas vinculadas de tu plan actual. Para conectar más redes sociales, por favor mejorá a un Plan Pro."
                }, status=400)
                
            return Response({
                "success": False,
                "error": f"Error al vincular: {err_text}"
            }, status=500)
        
        platform = request.data.get('platform')
        
        jwt_payload = {
            "username": username,
            "redirect_url": f"{settings.FRONTEND_URL}/conexiones",
            "logo_image": "https://res.cloudinary.com/dpqgbgilw/image/upload/leadbook_logo",
            "connect_title": "Conectá tus redes sociales",
            "connect_description": "Conectá tus cuentas para publicar automáticamente con LeadBook",
            "show_calendar": True
        }
        # Si viene una plataforma específica, pre-seleccionarla en el wizard de UploadPost
        if platform:
            jwt_payload["platform"] = platform
            
        jwt_resp = http_requests.post(
            "https://api.upload-post.com/api/uploadposts/users/generate-jwt",
            headers=headers,
            json=jwt_payload,
            timeout=10
        )
        print(f"[conexiones_init] generate_jwt status={jwt_resp.status_code}", flush=True)
        if jwt_resp.status_code != 200:
            return Response({
                "success": False,
                "error": f"Error generando URL: {jwt_resp.text[:200]}"
            }, status=500)
        
        data = jwt_resp.json()
        return Response({
            "success": True,
            "access_url": data.get("access_url"),
            "username": username
        })
    except Exception as e:
        print(f"[conexiones_init] EXCEPTION: {e}", file=sys.stderr, flush=True)
        traceback.print_exc(file=sys.stderr)
        return Response({
            "success": False,
            "error": f"Error interno del servidor: {str(e)[:200]}"
        }, status=500)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def conexiones_eliminar(request):
    """
    Elimina el perfil del usuario en UploadPost (desvincula todas las redes y libera el límite de la API).
    """
    try:
        from api.pool_manager import get_api_key
        user = request.user
        username = f"leadbook_{user.id}"
        api_key = get_api_key(user, 'uploadpost')
        
        if not api_key:
            return Response({"success": False, "error": "No se encontró API Key vinculada para este usuario"}, status=400)
            
        headers = {
            "Authorization": f"Apikey {api_key}",
            "Content-Type": "application/json"
        }
        
        resp = http_requests.delete(
            "https://api.upload-post.com/api/uploadposts/users",
            headers=headers,
            json={"username": username},
            timeout=10
        )
        
        if resp.status_code in [200, 204]:
            return Response({"success": True, "message": "Perfil eliminado. Podés volver a vincular tus cuentas."})
        else:
            return Response({"success": False, "error": f"Error al eliminar: {resp.text[:200]}"}, status=400)
            
    except Exception as e:
        return Response({"success": False, "error": f"Error interno: {str(e)[:100]}"}, status=500)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def conexiones_estado(request):
    """
    Devuelve las redes sociales conectadas del usuario consultando UploadPost.
    Siempre devuelve JSON — nunca HTML.
    """
    import traceback, sys, os
    try:
        from api.pool_manager import get_api_key
        from django.conf import settings

        user = request.user
        username = f"leadbook_{user.id}"
        print(f"[conexiones_estado] user={user.email} username={username}", flush=True)

        # 1. Key del pool del usuario
        api_key = get_api_key(user, 'uploadpost')

        # 2. Fallback a key global de .env
        if not api_key:
            api_key = (
                getattr(settings, 'UPLOADPOST_API_KEY', '') or
                os.environ.get('UPLOADPOST_API_KEY', '') or
                os.environ.get('UPLOAD_POST_API_KEY', '')
            ) or None
            if api_key:
                print(f"[conexiones_estado] Usando key global para {user.email}", flush=True)

        if not api_key:
            print(f"[conexiones_estado] Sin key uploadpost para {user.email}", flush=True)
            return Response({"success": True, "redes": [], "conectado": False})

        headers = {
            "Authorization": f"Apikey {api_key}",
            "Content-Type": "application/json"
        }

        # ESTRATEGIA 1: Endpoint específico del usuario (más preciso)
        perfil = None
        resp_individual = http_requests.get(
            f"https://api.upload-post.com/api/uploadposts/users/{username}",
            headers=headers,
            timeout=10
        )
        print(f"[conexiones_estado] GET /users/{username} → status={resp_individual.status_code}", flush=True)

        if resp_individual.status_code == 200:
            try:
                perfil = resp_individual.json()
                print(f"[conexiones_estado] perfil individual={perfil}", flush=True)
            except Exception:
                perfil = None

        # ESTRATEGIA 2: Listar todos y buscar (fallback)
        if not perfil:
            resp_list = http_requests.get(
                "https://api.upload-post.com/api/uploadposts/users",
                headers=headers,
                timeout=10
            )
            print(f"[conexiones_estado] GET /users list → status={resp_list.status_code}", flush=True)
            if resp_list.status_code == 200:
                try:
                    raw = resp_list.json()
                    print(f"[conexiones_estado] raw list response (first 500 chars)={str(raw)[:500]}", flush=True)
                    # Normalizar a lista
                    if isinstance(raw, list):
                        usuarios = raw
                    elif isinstance(raw, dict):
                        usuarios = raw.get('users') or raw.get('data') or raw.get('results') or []
                    else:
                        usuarios = []
                    perfil = next(
                        (u for u in usuarios if u.get("username") == username),
                        None
                    )
                except Exception as parse_err:
                    print(f"[conexiones_estado] Error parseando lista: {parse_err}", flush=True)

        if not perfil:
            print(f"[conexiones_estado] Perfil '{username}' no encontrado en UploadPost", flush=True)
            return Response({"success": True, "redes": [], "conectado": False, "username": username})

        # Obtener el objeto de redes.
        # UploadPost devuelve {"success": true, "profile": {"social_accounts": {"instagram": {...}, "tiktok": ""}}}
        if "profile" in perfil:
            social_accounts = perfil["profile"].get("social_accounts", {})
        else:
            social_accounts = perfil.get("social_accounts", {})

        print(f"[conexiones_estado] social_accounts={social_accounts}", flush=True)

        redes_normalizadas = []
        
        # Iterar sobre las claves del diccionario (ej: "instagram", "tiktok")
        if isinstance(social_accounts, dict):
            for platform, data in social_accounts.items():
                # Si el valor está vacío (ej: ""), significa que no está conectado
                if not data:
                    continue
                    
                # Si es un dict, extraer la info
                if isinstance(data, dict):
                    # Ignorar si requiere reconexión
                    if data.get("reauth_required") is True:
                        continue
                        
                    redes_normalizadas.append({
                        "platform": platform,
                        "username": data.get("handle") or data.get("display_name") or data.get("username") or "",
                        "status": "connected"
                    })
                elif isinstance(data, str) and data:
                    # Por si acaso devuelve un string no vacío
                    redes_normalizadas.append({
                        "platform": platform,
                        "username": data,
                        "status": "connected"
                    })

        return Response({
            "success": True,
            "conectado": len(redes_normalizadas) > 0,
            "redes": redes_normalizadas,
            "username": username,
            "total": len(redes_normalizadas)
            # Removemos debug_raw_perfil porque ya vimos la estructura
        })

    except Exception as e:
        print(f"[conexiones_estado] EXCEPTION: {e}", file=sys.stderr, flush=True)
        traceback.print_exc(file=sys.stderr)
        return Response({
            "success": False,
            "redes": [],
            "conectado": False,
            "error": f"Error interno: {str(e)[:200]}"
        }, status=500)



# ============================================================
# DEBUG / DIAGNÓSTICO — endpoints seguros (no exponen secretos)
# Uso: curl https://tuback.up.railway.app/api/v1/debug/email-check/
# ============================================================

@api_view(['GET'])
@permission_classes([AllowAny])
def debug_uploadpost(request, username):
    """
    Endpoint temporal para ver la estructura exacta que devuelve UploadPost
    para un usuario específico.
    """
    import os
    from django.conf import settings
    
    api_key = (
        getattr(settings, 'UPLOADPOST_API_KEY', '') or
        os.environ.get('UPLOADPOST_API_KEY', '') or
        os.environ.get('UPLOAD_POST_API_KEY', '')
    )
    
    if not api_key:
        return Response({"error": "No global UPLOADPOST_API_KEY"}, status=500)
        
    headers = {
        "Authorization": f"Apikey {api_key}",
        "Content-Type": "application/json"
    }
    
    # Probar endpoint individual
    resp1 = http_requests.get(
        f"https://api.upload-post.com/api/uploadposts/users/{username}",
        headers=headers,
        timeout=10
    )
    
    # Probar endpoint lista
    resp2 = http_requests.get(
        "https://api.upload-post.com/api/uploadposts/users",
        headers=headers,
        timeout=10
    )
    
    list_data = None
    if resp2.status_code == 200:
        try:
            raw = resp2.json()
            if isinstance(raw, list): usuarios = raw
            elif isinstance(raw, dict): usuarios = raw.get('users') or raw.get('data') or raw.get('results') or []
            else: usuarios = []
            list_data = next((u for u in usuarios if u.get("username") == username), None)
        except: pass
        
    return Response({
        "target_username": username,
        "strategy_1_individual": {
            "status": resp1.status_code,
            "data": resp1.json() if resp1.status_code == 200 else resp1.text[:200]
        },
        "strategy_2_list": {
            "status": resp2.status_code,
            "found_in_list": list_data
        }
    })

@api_view(['GET'])
@permission_classes([AllowAny])
def debug_email_check(request):
    """
    Devuelve metadata de la config de email sin exponer la password.
    Sirve para verificar si las env vars GMAIL_USER y GMAIL_APP_PASSWORD
    están cargadas en Railway (o cualquier entorno).
    """
    from django.conf import settings
    host_user = getattr(settings, 'EMAIL_HOST_USER', '') or ''
    host_pass = getattr(settings, 'EMAIL_HOST_PASSWORD', '') or ''

    # Enmascarar el user (mostrar solo primeros/últimos chars)
    def mask(s, head=3, tail=3):
        if not s:
            return None
        if len(s) <= head + tail:
            return "*" * len(s)
        return f"{s[:head]}***{s[-tail:]}"

    import os
    provider    = (os.environ.get("EMAIL_PROVIDER") or getattr(settings, "EMAIL_PROVIDER", "") or "gmail").strip().lower()
    resend_key  = os.environ.get("RESEND_API_KEY") or getattr(settings, "RESEND_API_KEY", "") or ""
    resend_from = os.environ.get("RESEND_FROM") or getattr(settings, "RESEND_FROM", "") or ""

    # Verdict operativo unificado
    if provider == "resend":
        if resend_key:
            verdict = "RESEND-OK-listo-para-enviar"
        else:
            verdict = "RESEND-seleccionado-pero-falta-RESEND_API_KEY"
    else:
        if bool(host_user) and bool(host_pass):
            verdict = "SMTP-OK-listo-para-enviar"
        else:
            verdict = "CONSOLE-BACKEND-emails-NO-saldran-cargar-GMAIL_APP_PASSWORD"

    return Response({
        "EMAIL_PROVIDER": provider,
        "EMAIL_BACKEND": getattr(settings, 'EMAIL_BACKEND', None),
        "EMAIL_HOST": getattr(settings, 'EMAIL_HOST', None),
        "EMAIL_PORT": getattr(settings, 'EMAIL_PORT', None),
        "EMAIL_USE_SSL": getattr(settings, 'EMAIL_USE_SSL', None),
        "EMAIL_USE_TLS": getattr(settings, 'EMAIL_USE_TLS', None),
        "DEFAULT_FROM_EMAIL": getattr(settings, 'DEFAULT_FROM_EMAIL', None),
        "GMAIL_USER_set": bool(host_user),
        "GMAIL_USER_masked": mask(host_user),
        "GMAIL_APP_PASSWORD_set": bool(host_pass),
        "GMAIL_APP_PASSWORD_len": len(host_pass),
        "RESEND_API_KEY_set": bool(resend_key),
        "RESEND_API_KEY_len": len(resend_key),
        "RESEND_FROM": resend_from or None,
        "CELERY_TASK_ALWAYS_EAGER": getattr(settings, 'CELERY_TASK_ALWAYS_EAGER', None),
        "DEBUG": getattr(settings, 'DEBUG', None),
        "verdict": verdict,
    })


@api_view(['POST'])
@permission_classes([AllowAny])
def debug_email_send(request):
    """
    Dispara un envío SMTP REAL y SINCRÓNICO de prueba.
    Body JSON: {"email": "destino@mail.com"}  (acepta también "to")
    Devuelve exactamente lo que pasó, incluyendo error SMTP completo si falla.

    IMPORTANTE: En producción deberías proteger este endpoint con
    X-Admin-Key antes de dejarlo abierto. Aquí queda AllowAny para debug rápido.
    """
    import traceback, socket, smtplib, ssl, time
    from django.conf import settings
    from django.core.mail import get_connection, EmailMultiAlternatives

    # Aceptar "email" o "to" (compatibilidad)
    destino = (request.data.get('email') or request.data.get('to') or '').strip().lower()
    if not destino:
        return Response({"error": "falta campo 'email' con el email destino"}, status=400)

    # Provider opcional — si se pasa "resend", probamos Resend sin tocar env vars
    forced_provider = (request.data.get('provider') or '').strip().lower()
    if forced_provider == 'resend':
        import os, traceback
        try:
            from .tasks import _send_via_resend
        except Exception as e_imp:
            return Response({
                "ok": False, "stage": "import-resend",
                "error_type": type(e_imp).__name__, "error": str(e_imp),
            }, status=500)
        print(f"[DEBUG-EMAIL] Forzando envío via RESEND a {destino}", flush=True)
        subject = "LeadBook — prueba de email (Resend, debug)"
        text_body = "Este es un email de prueba enviado por /api/v1/debug/email-send/ (provider=resend)."
        html_body = (
            "<p>Este es un email de prueba enviado por <code>/api/v1/debug/email-send/</code> "
            "(<b>provider=resend</b>).</p><p>Si lo estás leyendo, Resend funciona desde este servidor.</p>"
        )
        try:
            ok, detalle = _send_via_resend(destino, subject, text_body, html_body)
            return Response({
                "ok": ok,
                "stage": "resend",
                "result": detalle,
                "destino": destino,
                "provider": "resend",
                "RESEND_API_KEY_set": bool(os.environ.get("RESEND_API_KEY") or getattr(settings, "RESEND_API_KEY", "")),
                "RESEND_FROM": os.environ.get("RESEND_FROM") or getattr(settings, "RESEND_FROM", "") or None,
            }, status=200 if ok else 500)
        except Exception as e_res:
            return Response({
                "ok": False, "stage": "resend",
                "error_type": type(e_res).__name__, "error": str(e_res),
                "traceback": traceback.format_exc()[-1500:],
            }, status=500)

    host      = getattr(settings, 'EMAIL_HOST', '')
    port      = getattr(settings, 'EMAIL_PORT', 0)
    use_ssl   = getattr(settings, 'EMAIL_USE_SSL', False)
    use_tls   = getattr(settings, 'EMAIL_USE_TLS', False)
    host_user = getattr(settings, 'EMAIL_HOST_USER', '') or ''
    host_pass = getattr(settings, 'EMAIL_HOST_PASSWORD', '') or ''
    from_addr = getattr(settings, 'DEFAULT_FROM_EMAIL', host_user)

    info = {
        "destino": destino,
        "backend": settings.EMAIL_BACKEND,
        "host": host,
        "port": port,
        "use_ssl": use_ssl,
        "use_tls": use_tls,
        "user_set": bool(host_user),
        "user_masked": (host_user[:3] + "***" + host_user[-3:]) if host_user else None,
        "pass_set": bool(host_pass),
        "pass_len": len(host_pass),
        "from": from_addr,
    }

    print(f"[DEBUG-EMAIL] Disparando envío de test a {destino} — host={host}:{port} ssl={use_ssl} tls={use_tls}", flush=True)

    # Guardas tempranas
    if not host_user or not host_pass:
        return Response({
            "ok": False,
            "stage": "env-vars",
            "error": "GMAIL_USER o GMAIL_APP_PASSWORD no están cargadas en el entorno",
            **info,
        }, status=500)

    # 1) Prueba de conectividad TCP pura
    t0 = time.time()
    try:
        sock = socket.create_connection((host, port), timeout=15)
        sock.close()
        tcp_ok = True
        tcp_ms = int((time.time() - t0) * 1000)
    except Exception as e_tcp:
        return Response({
            "ok": False,
            "stage": "tcp-connect",
            "error_type": type(e_tcp).__name__,
            "error": str(e_tcp),
            "hint": "Railway no puede abrir el puerto SMTP. Gmail en la nube suele fallar aquí → migrar a Resend.",
            **info,
        }, status=500)

    # 2) Handshake SMTP + login con smtplib directo para capturar respuesta exacta del server
    smtp_debug = {"tcp_ok": tcp_ok, "tcp_ms": tcp_ms}
    try:
        ctx = ssl.create_default_context()
        if use_ssl:
            smtp = smtplib.SMTP_SSL(host, port, timeout=30, context=ctx)
        else:
            smtp = smtplib.SMTP(host, port, timeout=30)
            if use_tls:
                smtp.starttls(context=ctx)
        ehlo_code, ehlo_msg = smtp.ehlo()
        smtp_debug["ehlo_code"] = ehlo_code
        smtp_debug["ehlo_msg"] = (ehlo_msg or b"").decode(errors="ignore")[:200]

        smtp.login(host_user, host_pass)
        smtp_debug["login"] = "ok"
        smtp.quit()
    except smtplib.SMTPAuthenticationError as e_auth:
        return Response({
            "ok": False,
            "stage": "smtp-auth",
            "error_type": "SMTPAuthenticationError",
            "smtp_code": e_auth.smtp_code,
            "smtp_error": (e_auth.smtp_error or b"").decode(errors="ignore"),
            "hint": "Gmail rechazó la autenticación. Si el app password es correcto y el usuario tiene 2FA, probablemente Google está bloqueando IPs de Railway → migrar a Resend.",
            "debug": smtp_debug,
            **info,
        }, status=500)
    except Exception as e_smtp:
        return Response({
            "ok": False,
            "stage": "smtp-handshake",
            "error_type": type(e_smtp).__name__,
            "error": str(e_smtp),
            "traceback": traceback.format_exc()[-1500:],
            "hint": "Falló el handshake SSL/TLS con Gmail. Probablemente Railway bloquea → migrar a Resend.",
            "debug": smtp_debug,
            **info,
        }, status=500)

    # 3) Si llegamos acá, SMTP está OK. Enviamos el mail real.
    try:
        connection = get_connection(
            backend="django.core.mail.backends.smtp.EmailBackend",
            host=host, port=port,
            username=host_user, password=host_pass,
            use_ssl=use_ssl, use_tls=use_tls,
            fail_silently=False,
            timeout=30,
        )
        msg = EmailMultiAlternatives(
            subject="LeadBook — prueba de email (debug)",
            body="Este es un email de prueba enviado por /api/v1/debug/email-send/.\nSi lo estás leyendo, SMTP funciona desde este servidor.",
            from_email=from_addr,
            to=[destino],
            connection=connection,
        )
        msg.attach_alternative(
            "<p>Este es un email de prueba enviado por <code>/api/v1/debug/email-send/</code>.</p>"
            "<p>Si lo estás leyendo, <b>SMTP funciona</b> desde este servidor.</p>",
            "text/html",
        )
        sent = msg.send(fail_silently=False)
        return Response({
            "ok": True,
            "stage": "sent",
            "sent_count": sent,
            "debug": smtp_debug,
            **info,
            "nota": "Si 'sent_count'=1 Gmail aceptó el mensaje. Revisá inbox y spam del destino.",
        })
    except Exception as e_send:
        return Response({
            "ok": False,
            "stage": "send-message",
            "error_type": type(e_send).__name__,
            "error": str(e_send),
            "traceback": traceback.format_exc()[-1500:],
            "debug": smtp_debug,
            **info,
        }, status=500)


@api_view(['GET'])
@permission_classes([AllowAny])
def proxy_pdf_view(request, listado_id):
    """
    Sirve el PDF desde Cloudinary actuando como proxy para evitar errores 401/ACL.
    Si el PDF es local (fallback), redirige a la URL local.
    """
    try:
        from .models import Listado
        listado = Listado.objects.get(id=listado_id)
        
        # Buscar URL en los datos del listado
        res = listado.datos.get('resultados', {}) if listado.datos else {}
        pdf_data = res.get('pdf', {})
        pdf_url = pdf_data.get('url') if isinstance(pdf_data, dict) else pdf_data
        
        if not pdf_url:
            return Response({"error": "URL de PDF no encontrada"}, status=404)

        # Si es URL local, redirigir directamente al endpoint que sirve el archivo
        if not pdf_url.startswith('http'):
            from django.shortcuts import redirect
            absolute_url = request.build_absolute_uri(pdf_url)
            if 'localhost' not in absolute_url and '127.0.0.1' not in absolute_url:
                absolute_url = absolute_url.replace('http://', 'https://')
            return redirect(absolute_url)

        # Petición interna a Cloudinary
        response = requests.get(pdf_url, stream=True, timeout=30)
        
        if response.status_code != 200:
            return Response({
                "error": f"Cloudinary respondió con error {response.status_code}"
            }, status=status.HTTP_502_BAD_GATEWAY)

        django_response = StreamingHttpResponse(
            response.iter_content(chunk_size=8192),
            content_type='application/pdf'
        )
        django_response['Content-Disposition'] = f'inline; filename="ficha_leadbook_{listado_id}.pdf"'
        return django_response

    except Listado.DoesNotExist:
        return Response({"error": "Listado no encontrado"}, status=404)
    except Exception as e:
        return Response({"error": str(e)}, status=500)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def descargar_pdf(request, listado_id):
    try:
        from .models import Listado
        from django.http import HttpResponse
        from django.shortcuts import get_object_or_404
        listado = get_object_or_404(Listado, id=listado_id, agente=request.user)
        datos = listado.datos or {}
        pdf_data = datos.get('resultados', {}).get('pdf', {})
        html_content = pdf_data.get('html', '') if isinstance(pdf_data, dict) else ''
        if not html_content:
            return Response({"error": "No hay PDF generado para este listado"}, status=404)
        from api.services.render_engine import render_html_to_pdf
        pdf_bytes = render_html_to_pdf(html_content)
        if not pdf_bytes:
            return Response({"error": "Error al generar PDF"}, status=500)
        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="ficha_leadbook_{listado_id}.pdf"'
        response['Access-Control-Allow-Origin'] = '*'
        return response
    except Listado.DoesNotExist:
        return Response({"error": "Listado no encontrado"}, status=404)
    except Exception as e:
        logger.error(f"Error en descargar_pdf: {e}")
        return Response({"error": str(e)}, status=500)

@api_view(['GET'])
@permission_classes([AllowAny])
def proxy_pdf_thumbnail_view(request, listado_id):
    """
    Genera una vista previa (imagen) de la primera página del PDF vía proxy.
    """
    try:
        from .models import Listado
        listado = Listado.objects.get(id=listado_id)
        res = listado.datos.get('resultados', {}) if listado.datos else {}
        pdf_data = res.get('pdf', {})
        pdf_url = pdf_data.get('url') if isinstance(pdf_data, dict) else pdf_data

        if not pdf_url or not pdf_url.startswith('http') or 'res.cloudinary.com' not in pdf_url:
            from django.shortcuts import redirect
            return redirect('https://placehold.co/400x600/111111/FFFFFF/png?text=Vista+Previa\\nNo+Disponible')

        thumb_url = pdf_url.replace('.pdf', '.jpg')
        if '/upload/' in thumb_url:
            thumb_url = thumb_url.replace('/upload/', '/upload/w_600,h_800,c_fill,pg_1/')

        response = requests.get(thumb_url, stream=True, timeout=15)
        
        if response.status_code != 200:
            return Response({"error": "No se pudo generar miniatura"}, status=404)

        return StreamingHttpResponse(
            response.iter_content(chunk_size=8192),
            content_type='image/jpeg'
        )

    except Exception as e:
        return Response({"error": str(e)}, status=500)

from django.shortcuts import get_object_or_404
from django.http import HttpResponse

@api_view(['GET'])
def generar_html(request, pk):
    from .models import Listado
    listado = get_object_or_404(Listado, pk=pk)
    data = listado.datos or {}
    context, temp_files, _, _, _ = construir_contexto_pdf(data, listado.agente, request)
    
    from django.template.loader import render_to_string
    try:
        html_string = render_to_string('pdf/property_brochure_html.html', context)
        # Limpiar temp files ya que no generamos PDF
        import os
        for f in temp_files:
            try:
                if os.path.exists(f):
                    os.remove(f)
            except Exception:
                pass
        return HttpResponse(html_string, content_type='text/html')
    except Exception as e:
        import traceback
        for f in temp_files:
            try:
                if os.path.exists(f):
                    os.remove(f)
            except Exception:
                pass
        return HttpResponse(f"Error generando HTML: {str(e)}<br><pre>{traceback.format_exc()}</pre>", content_type='text/html', status=500)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generar_escena(request):
    """Regenera el texto de UNA escena específica usando el mismo tono/voz del usuario."""
    data = request.data
    nombre_escena = data.get('nombre_escena', 'Escena')
    indice_escena = data.get('indice_escena', 0)
    total_escenas = data.get('total_escenas', 4)

    tipo = data.get('tipoPropiedad', 'Propiedad')
    ciudad = data.get('ciudad', '')
    operacion = data.get('operacion', 'Venta')
    moneda = data.get('moneda', 'USD')
    precio = data.get('precio', '')
    voz = data.get('voz', 'femenina')
    tono = data.get('tono', 'profesional')
    tipo_video = data.get('tipoVideo', 'reel')
    contexto_adicional = data.get('contextoAdicional', '')

    tono_map = {
        'profesional': 'profesional y formal, transmite confianza',
        'lujo': 'de lujo y exclusividad, sofisticado, usa vocabulario refinado',
        'energetico': 'dinámico y energético, usa frases cortas e impactantes',
    }
    tono_instrucciones = tono_map.get(tono, tono_map['profesional'])
    narrador = 'firme, directo, con autoridad' if voz == 'masculina' else 'cálido, cercano, invitador'
    palabras = '25-38' if tipo_video == 'reel' else '50-75'
    contexto_extra = f"\nEnfoque adicional: {contexto_adicional}" if contexto_adicional else ''

    prompt = f"""Sos un copywriter inmobiliario experto.
Generá SOLO el texto para la escena "{nombre_escena}" (escena {indice_escena + 1} de {total_escenas}) de un video inmobiliario.

PROPIEDAD: {tipo} en {operacion} | {ciudad} | {moneda} {precio}
TONO: {tono_instrucciones}
NARRADOR: {narrador}{contexto_extra}

REQUISITOS:
- Exactamente {palabras} palabras
- El texto es para narración en voz en off, debe sonar natural al hablar
- No pongas el nombre de la escena, solo el texto a narrar
- Responde SOLO el texto, sin JSON, sin comillas, sin explicaciones"""

    try:
        result = call_gemini_api(prompt, agente=request.user)
        if not result:
            return Response({"error": "No se pudo generar texto"}, status=503)
        return Response({"texto": result.strip()})
    except Exception as e:
        return Response({"error": str(e)}, status=500)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def upload_fotos_listado(request):
    """
    Sube fotos de propiedad (portada y galería) a Cloudinary a través del pool del backend.
    """
    data = request.data
    portada_b64 = data.get('portadaUrl')
    fotos_b64 = data.get('fotosRecorrido', [])
    listado_id = data.get('listado_id')

    user_id = request.user.id
    response_data = {
        'portadaUrl': None,
        'fotosRecorrido': []
    }

    try:
        from api.services.almacenamiento import AlmacenamientoCloudinary
        
        if portada_b64 and isinstance(portada_b64, str) and portada_b64.startswith('data:image'):
            print(f"[UPLOAD] portada_b64 tipo: {type(portada_b64).__name__}, es base64: {bool(portada_b64 and isinstance(portada_b64, str) and portada_b64.startswith('data:image'))}")
            obj = AlmacenamientoCloudinary.guardar_foto_propiedad(portada_b64, user_id, listado_id, tipo_foto='portada')
            print(f"[UPLOAD] get_mejor_cuenta resultado: {AlmacenamientoCloudinary.get_mejor_cuenta()}")
            print(f"[UPLOAD] resultado upload portada: {obj}")
            if obj:
                response_data['portadaUrl'] = obj
            else:
                response_data['portadaUrl'] = portada_b64 # Fallback
        elif isinstance(portada_b64, dict):
            response_data['portadaUrl'] = portada_b64
        elif portada_b64 and isinstance(portada_b64, str) and portada_b64.startswith('http'):
            response_data['portadaUrl'] = portada_b64
            
        for i, foto in enumerate(fotos_b64):
            if foto and isinstance(foto, str) and foto.startswith('data:image'):
                obj = AlmacenamientoCloudinary.guardar_foto_propiedad(foto, user_id, listado_id, tipo_foto='galeria', indice=i)
                if obj:
                    response_data['fotosRecorrido'].append(obj)
            elif isinstance(foto, dict):
                response_data['fotosRecorrido'].append(foto)
            elif foto and isinstance(foto, str) and foto.startswith('http'):
                response_data['fotosRecorrido'].append(foto)

        return Response(response_data)
        
    except Exception as e:
        logger.error(f"Error al subir fotos de listado: {e}")
        return Response({"error": str(e)}, status=500)
    except Exception as e:
        return Response({"error": str(e)}, status=500)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def listar_notificaciones(request):
    from .models import Notificacion
    notifs = Notificacion.objects.filter(usuario=request.user)[:20]
    data = [{
        'id': n.id,
        'tipo': n.tipo,
        'titulo': n.titulo,
        'mensaje': n.mensaje,
        'leida': n.leida,
        'creada_en': n.creada_en.isoformat(),
    } for n in notifs]
    no_leidas = Notificacion.objects.filter(usuario=request.user, leida=False).count()
    return Response({'notificaciones': data, 'no_leidas': no_leidas})

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def marcar_notificacion_leida(request, notif_id):
    from .models import Notificacion
    notif = Notificacion.objects.filter(id=notif_id, usuario=request.user).first()
    if notif:
        notif.leida = True
        notif.save()
    return Response({'ok': True})

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def marcar_todas_leidas(request):
    from .models import Notificacion
    Notificacion.objects.filter(usuario=request.user, leida=False).update(leida=True)
    return Response({'ok': True})

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def estado_cuota_ia(request):
    from .models import UserAPIQuota, Suscripcion
    try:
        quota = UserAPIQuota.objects.get(user=request.user, service='gemini')
        agotada = quota.is_blocked
        usado = quota.requests_today
        limite = quota.daily_limit
    except UserAPIQuota.DoesNotExist:
        agotada = False
        usado = 0
        limite = 1500
    
    try:
        suscripcion = request.user.suscripcion
        ai_used = suscripcion.ai_used
    except:
        ai_used = usado

    return Response({
        'agotada': agotada,
        'usado': ai_used,
        'limite': limite,
        'porcentaje': min(100, int((ai_used / limite) * 100)) if limite > 0 else 0
    })

@api_view(['GET', 'POST'])
@permission_classes([AllowAny])
def debug_quota(request):
    from .models import UserAPIQuota, APIKey, APIBundleAssignment
    
    if request.method == 'POST':
        from .models import UserAPIQuota
        # Desbloquear todos los usuarios cuyo uso actual es menor al límite
        desbloqueados = 0
        for q in UserAPIQuota.objects.filter(is_blocked=True):
            if q.requests_today < q.daily_limit:
                q.is_blocked = False
                q.save()
                desbloqueados += 1
        # Corregir límites incorrectos por servicio
        UserAPIQuota.objects.filter(service='uploadpost', daily_limit__gt=100).update(daily_limit=10)
        UserAPIQuota.objects.filter(service='gemini', daily_limit__lt=100).update(daily_limit=1500)
        
        # Reset extras de prueba (pago_id = 'manual_admin')
        from .models import BundleAPIExtra
        extras_borradas = BundleAPIExtra.objects.filter(pago_id='manual_admin').delete()
        print(f"[DEBUG] Extras de prueba borradas: {extras_borradas}")
        
        return Response({'desbloqueados': desbloqueados})
    
    quotas = list(UserAPIQuota.objects.values(
        'user_id', 'service', 'daily_limit', 'monthly_limit', 
        'requests_today', 'is_blocked'
    ))
    assignments = APIBundleAssignment.objects.filter(activo=True).select_related('usuario', 'bundle__key_gemini')
    keys_info = []
    for a in assignments:
        k = a.bundle.key_gemini if a.bundle else None
        if k:
            keys_info.append({
                'user': a.usuario.email,
                'key_id': k.id,
                'daily_limit': k.daily_limit,
                'monthly_limit': k.monthly_limit,
                'status': k.status
            })
    return Response({'quotas': quotas, 'keys': keys_info})

```

### File: .\scratch\generate_audit.py
```python
import os
import psycopg2

DATABASE_URL = "postgresql://postgres:plsOyadKzrwUCjDtNhWllVyhUMzUwoci@shinkansen.proxy.rlwy.net:37371/railway"

FILES_TO_INCLUDE = [
    "api/models.py",
    "api/urls.py",
    "api/views.py",
    "api/views_admin.py",
    "api/serializers.py",
    "api/tasks.py",
    "subzero_core/settings.py"
]

def search_files(keyword, root_dir="."):
    matches = set()
    for dirpath, _, filenames in os.walk(root_dir):
        if 'venv' in dirpath or '__pycache__' in dirpath or '.git' in dirpath:
            continue
        for f in filenames:
            if not f.endswith('.py'):
                continue
            path = os.path.join(dirpath, f)
            try:
                with open(path, 'r', encoding='utf-8') as file:
                    if keyword in file.read():
                        matches.add(path)
            except Exception:
                pass
    return matches

def run_query(cursor, query):
    try:
        cursor.execute(query)
        if cursor.description:
            columns = [desc[0] for desc in cursor.description]
            rows = cursor.fetchall()
            return columns, rows
        return [], []
    except Exception as e:
        return ["Error"], [[str(e)]]

def format_table(columns, rows):
    if not columns:
        return "(Sin resultados)\n"
    
    col_widths = [max(len(str(item)) for item in col) for col in zip(*rows, columns)] if rows else [len(c) for c in columns]
    
    header = " | ".join(str(c).ljust(w) for c, w in zip(columns, col_widths))
    separator = "-+-".join("-" * w for w in col_widths)
    
    res = [header, separator]
    for row in rows:
        res.append(" | ".join(str(item).ljust(w) for item, w in zip(row, col_widths)))
    return "\n".join(res) + "\n"

def main():
    out_file = "project_audit.md"
    with open(out_file, 'w', encoding='utf-8') as f:
        f.write("# COMPLETE LEADBOOK PROJECT AUDIT\n\n")
        
        # 1. SQL QUERIES
        f.write("## DATABASE AUDIT (Production)\n\n")
        try:
            conn = psycopg2.connect(DATABASE_URL)
            with conn.cursor() as cur:
                queries = [
                    ("SQL QUERY 1 - Todas las tablas", "SELECT schemaname, tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename;"),
                    ("SQL QUERY 2 - Estructura completa de todas las tablas", "SELECT table_name, column_name, data_type, is_nullable, column_default FROM information_schema.columns WHERE table_schema = 'public' AND table_name LIKE 'api_%' ORDER BY table_name, ordinal_position;"),
                    ("SQL QUERY 3 - Todas las relaciones entre tablas", "SELECT tc.table_name, kcu.column_name, ccu.table_name AS foreign_table, ccu.column_name AS foreign_column FROM information_schema.table_constraints tc JOIN information_schema.key_column_usage kcu ON tc.constraint_name = kcu.constraint_name JOIN information_schema.constraint_column_usage ccu ON ccu.constraint_name = tc.constraint_name WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_name LIKE 'api_%' ORDER BY tc.table_name;"),
                    ("SQL QUERY 4.1 - Datos api_apikey (limit 5)", "SELECT * FROM api_apikey LIMIT 5;"),
                    ("SQL QUERY 4.2 - Datos api_userapiquota (limit 5)", "SELECT * FROM api_userapiquota LIMIT 5;"),
                    ("SQL QUERY 4.3 - Datos api_bundleapiextra (limit 5)", "SELECT * FROM api_bundleapiextra LIMIT 5;"),
                    ("SQL QUERY 4.4 - Datos api_apibundle (limit 5)", "SELECT * FROM api_apibundle LIMIT 5;"),
                    ("SQL QUERY 4.5 - Datos api_apibundleassignment (limit 5)", "SELECT * FROM api_apibundleassignment LIMIT 5;"),
                    ("SQL QUERY 4.6 - Datos api_suscripcion (limit 5)", "SELECT * FROM api_suscripcion LIMIT 5;"),
                ]
                
                for title, sql in queries:
                    f.write(f"### {title}\n")
                    f.write(f"```sql\n{sql}\n```\n")
                    cols, rows = run_query(cur, sql)
                    f.write("```text\n")
                    f.write(format_table(cols, rows))
                    f.write("```\n\n")
                    
        except Exception as e:
            f.write(f"**Database Connection Error:** {e}\n\n")
        finally:
            if 'conn' in locals() and conn:
                conn.close()

        # 2. FILE SEARCH FOR MERCADOPAGO / WEBHOOK
        f.write("## FILES CONTAINING 'mercadopago' OR 'webhook'\n\n")
        extra_files = search_files("mercadopago").union(search_files("webhook"))
        
        all_files_to_read = set(FILES_TO_INCLUDE).union(extra_files)
        
        # 3. SOURCE CODE
        f.write("## SOURCE CODE\n\n")
        for filepath in sorted(list(all_files_to_read)):
            f.write(f"### File: {filepath}\n")
            if os.path.exists(filepath):
                with open(filepath, 'r', encoding='utf-8') as src:
                    content = src.read()
                f.write(f"```python\n{content}\n```\n\n")
            else:
                f.write(f"*(File does not exist)*\n\n")

if __name__ == "__main__":
    main()

```

### File: api/models.py
```python
from django.db import models
from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin

class AgentManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('El email es obligatorio')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        return self.create_user(email, password, **extra_fields)

class Agent(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(unique=True)
    nombre = models.CharField(max_length=255)
    telefono = models.CharField(max_length=50, null=True, blank=True)
    agencia = models.CharField(max_length=255, null=True, blank=True)
    logo_url = models.TextField(null=True, blank=True)
    nombre_inmobiliaria = models.CharField(max_length=255, null=True, blank=True)
    meta_access_token = models.TextField(null=True, blank=True)
    meta_instagram_account_id = models.CharField(max_length=100, null=True, blank=True)
    nicho = models.CharField(max_length=100, null=True, blank=True)
    pais = models.CharField(max_length=100, null=True, blank=True)
    nacionalidad = models.CharField(max_length=100, null=True, blank=True)
    sitio_web = models.URLField(max_length=255, null=True, blank=True)
    bio = models.TextField(null=True, blank=True)
    agentes_asociados = models.JSONField(default=list)
    plan_nombre = models.CharField(
        max_length=20,
        choices=[('free','Free'),('starter','Starter'),
                 ('pro','Pro'),('scale','Scale'),('business','Business')],
        default='free'
    )
    plan_activo = models.BooleanField(default=True)
    mp_subscription_id = models.CharField(max_length=100, blank=True, null=True)
    mp_customer_id = models.CharField(max_length=100, blank=True, null=True)
    plan_seleccionado = models.BooleanField(default=False)
    plan = models.CharField(max_length=20, default='free')
    activo = models.BooleanField(default=True)
    fecha_registro = models.DateTimeField(auto_now_add=True)
    eliminado_en = models.DateTimeField(null=True, blank=True)

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    last_login_ip = models.GenericIPAddressField(null=True, blank=True)
    last_login_user_agent = models.TextField(null=True, blank=True)

    objects = AgentManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['nombre']

    def __str__(self):
        return self.email

class Property(models.Model):
    title = models.CharField(max_length=255)
    description = models.TextField()
    price = models.DecimalField(max_digits=12, decimal_places=2)
    address = models.CharField(max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title

class PropertyImage(models.Model):
    property = models.ForeignKey(Property, related_name='images', on_delete=models.CASCADE)
    image = models.ImageField(upload_to='properties/')
    is_main = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Image for {self.property.title}"

class GeneratedAsset(models.Model):
    ASSET_TYPES = [
        ('PDF', 'PDF Brochure'),
        ('VIDEO', 'Marketing Video'),
        ('EMAIL', 'Email Template'),
        ('SOCIAL', 'Social Media Image'),
    ]

    property = models.ForeignKey(Property, related_name='assets', on_delete=models.CASCADE)
    asset_type = models.CharField(max_length=10, choices=ASSET_TYPES)
    file = models.FileField(upload_to='assets/', null=True, blank=True)
    status = models.CharField(max_length=50, default='PENDING') # PENDING, PROCESSING, COMPLETED, FAILED
    error_message = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.get_asset_type_display()} for {self.property.title}"

class Listado(models.Model):
    agente = models.ForeignKey(Agent, on_delete=models.CASCADE, related_name='listados')
    titulo = models.CharField(max_length=255)
    tipo_propiedad = models.CharField(max_length=100)
    ciudad = models.CharField(max_length=100)
    precio = models.CharField(max_length=50)
    datos = models.JSONField(default=dict)
    video_url = models.URLField(max_length=500, null=True, blank=True)
    video_status = models.CharField(max_length=50, default='none')
    creado_en = models.DateTimeField(auto_now_add=True)
    videos_creados = models.IntegerField(default=0)
    
    class Meta:
        ordering = ['-creado_en']

    def __str__(self):
        return f"{self.titulo} - {self.agente.email}"

class Plan(models.Model):
    PLAN_CHOICES = [('starter','Starter'),('pro','Pro'),('premium','Premium')]
    nombre = models.CharField(max_length=20, choices=PLAN_CHOICES, unique=True)
    precio_usd = models.DecimalField(max_digits=6, decimal_places=2)
    properties_per_month = models.IntegerField(default=20)
    ai_generations = models.IntegerField(default=50)
    image_generations = models.IntegerField(default=20)
    video_generations = models.IntegerField(default=0)
    auto_posting = models.BooleanField(default=False)
    voice_ai = models.BooleanField(default=False)
    branding = models.BooleanField(default=False)
    priority_support = models.BooleanField(default=False)
    mp_plan_id = models.CharField(max_length=100, null=True, blank=True)
    # Soporte para billing diferenciado mensual/anual
    mp_price_id_mensual = models.CharField(max_length=100, null=True, blank=True)
    mp_price_id_anual = models.CharField(max_length=100, null=True, blank=True)

class Suscripcion(models.Model):
    agente = models.OneToOneField(Agent, on_delete=models.CASCADE, related_name='suscripcion')
    plan = models.ForeignKey(Plan, on_delete=models.SET_NULL, null=True)
    periodo_inicio = models.DateTimeField(auto_now_add=True)
    periodo_fin = models.DateTimeField(null=True, blank=True)
    mp_subscription_id = models.CharField(max_length=100, null=True, blank=True)
    mp_preapproval_id = models.CharField(max_length=100, null=True, blank=True)
    mp_status = models.CharField(max_length=30, default='free')
    properties_used = models.IntegerField(default=0)
    ai_used = models.IntegerField(default=0)
    images_used = models.IntegerField(default=0)
    videos_used = models.IntegerField(default=0)
    extra_credits = models.IntegerField(default=0)
    activa = models.BooleanField(default=True)

import hashlib

class OTPCode(models.Model):
    email = models.EmailField()
    code_hash = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    attempts = models.IntegerField(default=0)
    verified = models.BooleanField(default=False)
    tipo = models.CharField(max_length=20, default='registro') # registro o recuperacion

    class Meta:
        ordering = ['-created_at']

    @staticmethod
    def hash_code(code: str) -> str:
        return hashlib.sha256(code.encode()).hexdigest()

    def is_expired(self) -> bool:
        from django.utils import timezone
        return timezone.now() > self.expires_at

    def is_valid(self, code: str) -> bool:
        return (
            not self.verified and
            not self.is_expired() and
            self.attempts < 5 and
            self.code_hash == self.hash_code(code)
        )

class TerminosCondiciones(models.Model):
    titulo = models.CharField(max_length=255, default="Términos y Condiciones de Uso")
    contenido = models.TextField()
    version = models.CharField(max_length=10, default="1.0")
    fecha_actualizacion = models.DateTimeField(auto_now=True)
    activo = models.BooleanField(default=True)
    
    class Meta:
        ordering = ['-fecha_actualizacion']
    
    def __str__(self):
        return f"{self.titulo} v{self.version}"

class PoliticaPrivacidad(models.Model):
    titulo = models.CharField(max_length=255, default="Política de Privacidad")
    contenido = models.TextField()
    version = models.CharField(max_length=10, default="1.0")
    fecha_actualizacion = models.DateTimeField(auto_now=True)
    activo = models.BooleanField(default=True)
    
    class Meta:
        ordering = ['-fecha_actualizacion']
    
    def __str__(self):
        return f"{self.titulo} v{self.version}"

class AmenidadPreset(models.Model):
    agente = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE,
        related_name='amenidad_presets'
    )
    nombre = models.CharField(max_length=100)
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['nombre']
        unique_together = ['agente', 'nombre']

    def __str__(self):
        return f"{self.agente} — {self.nombre}"

class UsageLog(models.Model):
    TIPO_CHOICES = [
        ('ai', 'IA / Guion'),
        ('image', 'Imagen'),
        ('video', 'Video'),
    ]
    agent = models.ForeignKey(
        'Agent',
        on_delete=models.CASCADE,
        related_name='usage_logs'
    )
    tipo = models.CharField(max_length=10, choices=TIPO_CHOICES)
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['agent', 'tipo', 'fecha']),
        ]

    def __str__(self):
        return f"{self.agent} - {self.tipo} - {self.fecha.strftime('%Y-%m-%d')}"

class APIKey(models.Model):
    SERVICIOS = [
        ('gemini', 'Gemini'),
        ('elevenlabs', 'ElevenLabs'),
        ('uploadpost', 'Upload Post'),
        ('openai', 'OpenAI'),
        ('groq', 'Groq'),
        ('nvidia', 'NVIDIA NIM'),
        ('anthropic', 'Anthropic'),
        ('stability', 'Stability AI'),
        ('replicate', 'Replicate'),
        ('cloudinary', 'Cloudinary'),
        ('other', 'Otro'),
    ]
    STATUS_CHOICES = [
        ('available', 'Disponible'),
        ('in_bundle', 'En Bundle'),
        ('assigned', 'Asignada (legacy)'),
        ('exhausted', 'Agotada'),
        ('dead', 'Muerta'),
        ('disabled', 'Deshabilitada'),
    ]
    
    servicio = models.CharField(max_length=20, choices=SERVICIOS)
    api_key = models.TextField()
    label = models.CharField(max_length=100, blank=True, null=True, help_text='Nombre descriptivo interno')
    empresa = models.CharField(max_length=100, blank=True, null=True, help_text='Empresa/cuenta propietaria de la key')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='available')
    is_monthly_exhausted = models.BooleanField(default=False, help_text='Indica si llegó al límite 100% de cuota mensual real')
    
    # Legacy: asignación directa a un usuario (mantener por compatibilidad)
    assigned_to = models.ForeignKey(
        'Agent', null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='assigned_keys'
    )
    assigned_at = models.DateTimeField(null=True, blank=True)
    
    daily_limit = models.IntegerField(default=20)  # Free tier Gemini: 20 req/día
    monthly_limit = models.IntegerField(null=True, blank=True)
    requests_today = models.IntegerField(default=0)
    requests_this_month = models.IntegerField(default=0)
    total_requests = models.IntegerField(default=0)
    
    last_used_at = models.DateTimeField(null=True, blank=True)
    last_health_check = models.DateTimeField(null=True, blank=True)
    last_health_status = models.BooleanField(default=True)
    error_count = models.IntegerField(default=0)
    
    notes = models.TextField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['assigned_to', 'servicio'], 
                name='unique_service_per_user',
                condition=models.Q(assigned_to__isnull=False)
            )
        ]
        
    def __str__(self):
        label = self.label or self.api_key[:12] + '...'
        return f"[{self.get_servicio_display()}] {label} — {self.get_status_display()}"


class APIBundle(models.Model):
    """
    Un paquete de 3 APIs (gemini + elevenlabs + uploadpost).
    Se asigna como unidad a un usuario Free.
    """
    STATUS_CHOICES = [
        ('available', 'Disponible'),
        ('assigned', 'Asignado'),
        ('retired', 'Retirado'),
    ]
    nombre = models.CharField(max_length=100, help_text='Ej: Bundle #1 — Cuenta Google A')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='available')
    
    # Las 3 keys del bundle (pueden ser null si no está configurado)
    key_gemini = models.OneToOneField(
        APIKey, null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='bundle_gemini'
    )
    key_elevenlabs = models.OneToOneField(
        APIKey, null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='bundle_elevenlabs'
    )
    key_uploadpost = models.OneToOneField(
        APIKey, null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='bundle_uploadpost'
    )
    
    notas = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'API Bundle'
        verbose_name_plural = 'API Bundles'

    def __str__(self):
        return f"{self.nombre} [{self.get_status_display()}]"

    def is_complete(self):
        """Verifica que las 3 keys requeridas estén configuradas y saludables (no agotadas ni muertas)."""
        valid_statuses = ['available', 'assigned', 'in_bundle']
        
        if not all([self.key_gemini_id, self.key_elevenlabs_id, self.key_uploadpost_id]):
            return False
            
        return all([
            self.key_gemini.status in valid_statuses if self.key_gemini else False,
            self.key_elevenlabs.status in valid_statuses if self.key_elevenlabs else False,
            self.key_uploadpost.status in valid_statuses if self.key_uploadpost else False,
        ])

    def get_key_for(self, servicio):
        """Devuelve el valor de la API key para el servicio indicado."""
        mapping = {
            'gemini': self.key_gemini,
            'elevenlabs': self.key_elevenlabs,
            'uploadpost': self.key_uploadpost,
        }
        key_obj = mapping.get(servicio)
        return key_obj.api_key if key_obj else None


class APIBundleAssignment(models.Model):
    """
    Registro de qué bundle fue asignado a qué usuario y cuándo.
    Un usuario solo puede tener un bundle activo a la vez.
    """
    bundle = models.ForeignKey(
        APIBundle,
        on_delete=models.PROTECT,
        related_name='assignments'
    )
    usuario = models.OneToOneField(
        'Agent',
        on_delete=models.CASCADE,
        related_name='api_bundle_assignment'
    )
    asignado_en = models.DateTimeField(auto_now_add=True)
    liberado_en = models.DateTimeField(null=True, blank=True)
    activo = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Asignación de Bundle'
        verbose_name_plural = 'Asignaciones de Bundle'

    def __str__(self):
        return f"{self.bundle.nombre} → {self.usuario.email} ({'activo' if self.activo else 'liberado'})"

class APIRequestLog(models.Model):
    api_key = models.ForeignKey(APIKey, on_delete=models.CASCADE, related_name='logs')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='api_logs')
    service = models.CharField(max_length=50)
    endpoint = models.CharField(max_length=255)
    method = models.CharField(max_length=10, default='POST')
    status_code = models.IntegerField(null=True, blank=True)
    success = models.BooleanField(default=False)
    response_time_ms = models.IntegerField(default=0)
    tokens_used = models.IntegerField(null=True, blank=True)
    characters_used = models.IntegerField(null=True, blank=True)
    cost_estimate = models.DecimalField(max_digits=10, decimal_places=6, null=True, blank=True)
    error_message = models.TextField(null=True, blank=True)
    request_context = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

class UserAPIQuota(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='api_quotas')
    service = models.CharField(max_length=50)
    daily_limit = models.IntegerField(default=1500)
    monthly_limit = models.IntegerField(null=True, blank=True)
    requests_today = models.IntegerField(default=0)
    requests_this_month = models.IntegerField(default=0)
    is_blocked = models.BooleanField(default=False)
    blocked_reason = models.CharField(max_length=255, null=True, blank=True)
    last_reset_daily = models.DateTimeField(null=True, blank=True)
    last_reset_monthly = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        unique_together = ('user', 'service')

class AdminAlert(models.Model):
    TYPE_CHOICES = [
        ('quota_warning', 'Quota Warning'),
        ('api_dead', 'API Dead'),
        ('user_abuse', 'User Abuse'),
        ('high_error_rate', 'High Error Rate'),
    ]
    SEVERITY_CHOICES = [
        ('info', 'Info'),
        ('warning', 'Warning'),
        ('critical', 'Critical'),
    ]
    type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    severity = models.CharField(max_length=10, choices=SEVERITY_CHOICES, default='info')
    title = models.CharField(max_length=255)
    message = models.TextField()
    related_api_key = models.ForeignKey(APIKey, on_delete=models.SET_NULL, null=True, blank=True)
    related_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

class UserBanRecord(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='bans')
    banned_at = models.DateTimeField(auto_now_add=True)
    banned_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='banned_users')
    reason = models.TextField()
    is_active = models.BooleanField(default=True)

class BannedEmail(models.Model):
    email = models.EmailField(unique=True)
    banned_at = models.DateTimeField(auto_now_add=True)
    reason = models.TextField(blank=True, null=True)

    class Meta:
        verbose_name = "Email Baneado Permanentemente"
        verbose_name_plural = "Emails Baneados Permanentemente"

    def __str__(self):
        return self.email

from django.db.models.signals import post_save
from django.dispatch import receiver

@receiver(post_save, sender=Agent)
def assign_keys_on_register(sender, instance, created, **kwargs):
    if created and instance.plan_nombre == 'free':
        from api.services.pool_service import APIPoolService
        APIPoolService.assign_keys_to_user(instance)

class VideoMusic(models.Model):
    nombre = models.CharField(max_length=100)
    archivo = models.FileField(upload_to='assets/music/')
    duracion_segundos = models.FloatField(default=0)
    activo = models.BooleanField(default=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.nombre

class VideoSFX(models.Model):
    TIPOS = [
        ('swoosh', 'Swoosh'),
        ('impact', 'Impact'),
        ('camera', 'Camera'),
        ('other', 'Other'),
    ]
    nombre = models.CharField(max_length=100)
    tipo = models.CharField(max_length=20, choices=TIPOS, default='other')
    archivo = models.FileField(upload_to='assets/sfx/')
    activo = models.BooleanField(default=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"[{self.get_tipo_display()}] {self.nombre}"

class BannedIP(models.Model):
    ip_address = models.GenericIPAddressField(unique=True)
    banned_at = models.DateTimeField(auto_now_add=True)
    reason = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.ip_address
class ConfiguracionSistema(models.Model):
    clave = models.CharField(max_length=50, unique=True) # ej: 'watermark'
    valor = models.TextField(blank=True, null=True)     # opcional
    datos = models.JSONField(default=dict, blank=True)  # para guardar public_id, cloud_name, etc.
    actualizado_en = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.clave


class Notificacion(models.Model):
    TIPOS = [
        ('quota_agotada', 'Cuota agotada'),
        ('quota_80', 'Cuota al 80%'),
        ('contenido_generado', 'Contenido generado'),
        ('reset_creditos', 'Reset de créditos'),
        ('info', 'Información'),
    ]
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notificaciones')
    tipo = models.CharField(max_length=30, choices=TIPOS, default='info')
    titulo = models.CharField(max_length=200)
    mensaje = models.TextField()
    leida = models.BooleanField(default=False)
    creada_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-creada_en']

    def __str__(self):
        return f"{self.usuario} - {self.titulo}"


class BundleAPIExtra(models.Model):
    """APIs adicionales de Gemini compradas por el usuario"""
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='apis_extra')
    api_key = models.ForeignKey('APIKey', on_delete=models.SET_NULL, null=True, related_name='extras')
    servicio = models.CharField(max_length=50, default='gemini')
    activa = models.BooleanField(default=True)
    comprada_en = models.DateTimeField(auto_now_add=True)
    pago_id = models.CharField(max_length=200, null=True, blank=True)

    class Meta:
        ordering = ['-comprada_en']

    def __str__(self):
        return f"{self.usuario} - {self.servicio} extra ({self.comprada_en.date()})"

```

### File: api/serializers.py
```python
from rest_framework import serializers
from .models import (
    Property, PropertyImage, GeneratedAsset, Agent, 
    TerminosCondiciones, PoliticaPrivacidad
)

class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)

    class Meta:
        model = Agent
        fields = ('email', 'password', 'nombre', 'telefono', 'agencia')

    def create(self, validated_data):
        user = Agent.objects.create_user(
            email=validated_data['email'],
            password=validated_data['password'],
            nombre=validated_data['nombre'],
            telefono=validated_data.get('telefono', ''),
            agencia=validated_data.get('agencia', '')
        )
        return user

class PropertyImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = PropertyImage
        fields = '__all__'

class GeneratedAssetSerializer(serializers.ModelSerializer):
    class Meta:
        model = GeneratedAsset
        fields = '__all__'

class PropertySerializer(serializers.ModelSerializer):
    images = PropertyImageSerializer(many=True, read_only=True)
    assets = GeneratedAssetSerializer(many=True, read_only=True)

    class Meta:
        model = Property
        fields = '__all__'

class TerminosCondicionesSerializer(serializers.ModelSerializer):
    class Meta:
        model = TerminosCondiciones
        fields = ['id', 'titulo', 'contenido', 'version', 'fecha_actualizacion']

class PoliticaPrivacidadSerializer(serializers.ModelSerializer):
    class Meta:
        model = PoliticaPrivacidad
        fields = ['id', 'titulo', 'contenido', 'version', 'fecha_actualizacion']

```

### File: api/tasks.py
```python
from celery import shared_task
from django.utils import timezone
from .models import Property, APIKey, UserAPIQuota
from .services import generate_pdf_for_property, send_property_notification_email
from .services.pool_service import APIPoolService
import requests


# ============================================================
# EMAIL PROVIDER — Resend HTTP API (fallback a Gmail SMTP)
# ============================================================
def _send_via_resend(email, subject, text_body, html_body):
    """
    Envía email usando la API HTTP de Resend.
    Requiere env vars: RESEND_API_KEY y RESEND_FROM (o usa DEFAULT_FROM_EMAIL).
    Retorna (ok: bool, detalle: str).
    """
    import os, sys
    from django.conf import settings
    try:
        import resend
    except ImportError as e:
        print(f"[EMAIL] ERROR al enviar (resend): paquete 'resend' no instalado: {e}", flush=True)
        return False, f"ImportError:{e}"

    api_key = os.environ.get("RESEND_API_KEY") or getattr(settings, "RESEND_API_KEY", "")
    if not api_key:
        print("[EMAIL] ERROR al enviar (resend): falta RESEND_API_KEY", flush=True)
        return False, "missing:RESEND_API_KEY"

    resend.api_key = api_key
    from_addr = (
        os.environ.get("RESEND_FROM")
        or getattr(settings, "RESEND_FROM", "")
        or getattr(settings, "DEFAULT_FROM_EMAIL", "")
        or "onboarding@resend.dev"
    )

    print(f"[EMAIL] Intentando enviar via Resend a {email} (from={from_addr})", flush=True)
    try:
        params = {
            "from": from_addr,
            "to": [email],
            "subject": subject,
            "html": html_body,
            "text": text_body,
        }
        result = resend.Emails.send(params)
        rid = (result or {}).get("id") if isinstance(result, dict) else str(result)
        print(f"[EMAIL] Enviado correctamente a {email} via Resend (id={rid})", flush=True)
        sys.stdout.flush()
        return True, f"sent:resend:{rid}"
    except Exception as e:
        print(f"[EMAIL] ERROR al enviar (resend): {type(e).__name__}: {str(e)}", flush=True)
        sys.stdout.flush()
        return False, f"error:resend:{type(e).__name__}:{str(e)[:200]}"

@shared_task
def run_asset_generation(property_id):
    try:
        property_instance = Property.objects.get(id=property_id)

        # 1. Generate PDF
        generate_pdf_for_property(property_instance)

        # 2. Generate Video (Removed)

        # 3. Send Notification Email
        send_property_notification_email(property_instance)

        return f"Completed generation for Property ID: {property_id}"
    except Property.DoesNotExist:
        return f"Property with ID {property_id} does not exist."
    except Exception as e:
        return f"Failed generation for {property_id}: {str(e)}"


@shared_task
def send_otp_email_async(email, code):
    """
    Envía el OTP vía Gmail SMTP. Si no hay credenciales configuradas,
    cae a console backend (imprime el código en la consola del server)
    para que el desarrollo/testing no se bloquee.
    """
    import traceback
    from django.conf import settings
    from django.core.mail import get_connection, EmailMultiAlternatives

    subject = "Tu código de verificación - LeadBook"
    text_body = (
        f"Tu código de verificación es: {code}\n\n"
        "Expira en 10 minutos.\n\n"
        "Si no solicitaste este código, ignorá este email."
    )
    html_body = f"""
    <div style="font-family:Arial,sans-serif;max-width:480px;margin:auto;
                padding:24px;border:1px solid #eee;border-radius:12px;">
      <h2 style="color:#111;margin:0 0 16px;">Verificá tu email</h2>
      <p style="color:#444;font-size:14px;">
        Usá este código para completar tu registro en <b>LeadBook</b>:
      </p>
      <div style="font-size:32px;font-weight:700;letter-spacing:6px;
                  text-align:center;background:#f5f5f5;padding:16px;
                  border-radius:8px;margin:16px 0;">{code}</div>
      <p style="color:#888;font-size:12px;">
        Expira en 10 minutos. Si no lo solicitaste, ignorá este email.
      </p>
    </div>
    """

    import sys, os
    host_user = getattr(settings, "EMAIL_HOST_USER", "") or ""
    host_pass = getattr(settings, "EMAIL_HOST_PASSWORD", "") or ""
    backend   = getattr(settings, "EMAIL_BACKEND", "")
    provider  = (os.environ.get("EMAIL_PROVIDER") or getattr(settings, "EMAIL_PROVIDER", "") or "gmail").strip().lower()

    print(f"[EMAIL] Intentando enviar a {email} (provider={provider})", flush=True)
    print(
        f"[EMAIL] DIAG task backend={backend} "
        f"host={getattr(settings,'EMAIL_HOST','?')}:{getattr(settings,'EMAIL_PORT','?')} "
        f"ssl={getattr(settings,'EMAIL_USE_SSL',None)} "
        f"tls={getattr(settings,'EMAIL_USE_TLS',None)} "
        f"user_set={bool(host_user)} pass_set={bool(host_pass)} pass_len={len(host_pass)} "
        f"provider={provider}",
        flush=True,
    )

    # --- Path Resend (HTTP API) ---
    if provider == "resend":
        ok, detalle = _send_via_resend(email, subject, text_body, html_body)
        if ok:
            return detalle
        # si Resend falla, dejamos caer el código en logs y no seguimos a Gmail
        print(f"[EMAIL-FALLBACK] OTP para {email}: {code} (solo visible en logs)", flush=True)
        return detalle

    # --- Path Gmail SMTP (default) ---
    # Si faltan credenciales: fallback a consola. IMPORTANTE: en Railway esto
    # significa que el email NO LLEGA al usuario, solo se imprime en logs.
    if not host_user or not host_pass:
        print("=" * 60, flush=True)
        print(f"[EMAIL] ERROR al enviar: faltan GMAIL_USER o GMAIL_APP_PASSWORD en env vars", flush=True)
        print(f"[EMAIL-FALLBACK] OTP para {email}: {code} (solo visible en logs)", flush=True)
        print("=" * 60, flush=True)
        sys.stdout.flush()
        return f"console:{email}"

    try:
        connection = get_connection(
            backend="django.core.mail.backends.smtp.EmailBackend",
            host=settings.EMAIL_HOST,
            port=settings.EMAIL_PORT,
            username=host_user,
            password=host_pass,
            use_ssl=getattr(settings, "EMAIL_USE_SSL", True),
            use_tls=getattr(settings, "EMAIL_USE_TLS", False),
            timeout=20,
        )
        from_email = getattr(settings, "DEFAULT_FROM_EMAIL", host_user) or host_user
        msg = EmailMultiAlternatives(
            subject=subject,
            body=text_body,
            from_email=from_email,
            to=[email],
            connection=connection,
        )
        msg.attach_alternative(html_body, "text/html")
        result = msg.send(fail_silently=False)
        print(f"[EMAIL] Enviado correctamente a {email} (send_result={result})", flush=True)
        sys.stdout.flush()
        return f"sent:{email}"
    except Exception as e:
        print(f"[EMAIL] ERROR al enviar: {type(e).__name__}: {str(e)}", flush=True)
        traceback.print_exc()
        # Mostrar el código para no bloquear diagnóstico
        print(f"[EMAIL-FALLBACK] OTP para {email}: {code}", flush=True)
        sys.stdout.flush()
        return f"error:{type(e).__name__}:{str(e)[:120]}"

@shared_task
def health_check_all_keys():
    """Ejecuta un health check para cada API Key en el sistema"""
    keys = APIKey.objects.exclude(status__in=['disabled', 'dead'])
    for key in keys:
        try:
            if key.servicio == 'gemini':
                url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-lite:generateContent?key={key.api_key}"
                res = requests.post(url, json={"contents":[{"parts":[{"text":"hello"}]}]}, timeout=5)
                is_healthy = res.status_code == 200
            elif key.servicio == 'elevenlabs':
                url = "https://api.elevenlabs.io/v1/voices"
                res = requests.get(url, headers={"xi-api-key": key.api_key}, timeout=5)
                is_healthy = res.status_code == 200
            elif key.servicio == 'uploadpost':
                url = "https://api.upload-post.com/api/uploadposts/users"
                res = requests.get(url, headers={"Authorization": f"Apikey {key.api_key}"}, timeout=5)
                is_healthy = res.status_code == 200
            else:
                is_healthy = True # Desconocido, asume sano
                
            key.last_health_status = is_healthy
            key.last_health_check = timezone.now()
            
            if not is_healthy:
                key.error_count += 1
                if key.error_count >= 5:
                    APIPoolService.mark_key_dead(key)
            else:
                key.error_count = 0 # reset error count si está sana
            key.save()
            
        except Exception as e:
            key.last_health_status = False
            key.last_health_check = timezone.now()
            key.error_count += 1
            if key.error_count >= 5:
                APIPoolService.mark_key_dead(key)
            key.save()

@shared_task
def reset_daily_counters():
    """Se ejecuta cada noche a las 00:00 UTC para reiniciar cuotas"""
    APIKey.objects.update(requests_today=0)
    UserAPIQuota.objects.update(requests_today=0, last_reset_daily=timezone.now())

@shared_task
def reset_monthly_counters():
    """Se ejecuta cada 1 de mes para reiniciar cuotas"""
    APIKey.objects.update(requests_this_month=0)
    UserAPIQuota.objects.update(requests_this_month=0, last_reset_monthly=timezone.now())

```

### File: api/urls.py
```python
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView
from . import views
from . import views_usage
from .views import (
    PropertyViewSet, GeneratedAssetViewSet, generar_guion, generar_listado, 
    RegisterView, LogoutView, DashboardView, ListadosView, generar_pdf, 
    PerfilView, ListadoDetalleView, generar_imagen_post, generar_imagen_story, 
    generar_email, serve_pdf_file, mp_checkout, mp_webhook, get_plan_info_mp,
    OnboardingView, video_status, publicar_instagram, send_otp, verify_otp,
    generar_video, obtener_terminos, obtener_politica_privacidad,
    plan_status, seleccionar_plan_free, test_upload_avatar, generar_carrusel,
    amenidades_presets, recuperar_password, confirmar_recuperacion,
    publicar_redes_sociales, proxy_pdf_view, proxy_pdf_thumbnail_view,
    generar_html, generar_escena, CustomTokenObtainPairView,
    upload_fotos_listado
)
from .views_admin import (
    admin_metricas, admin_usuarios_list, admin_usuario_cambiar_plan, admin_usuario_eliminar,
    admin_usuario_detalle, admin_usuarios_eliminados, admin_usuario_restaurar,
    admin_usuario_suspender, admin_apikeys_resumen, admin_apikeys_pool,
    admin_apikeys_pool_crear, admin_apikeys_pool_bulk, admin_apikeys_pool_detail, admin_apikeys_global,
    admin_pool_estado, admin_alerts_read, admin_health_check, admin_enviar_email,
    admin_bundles_list, admin_bundles_crear, admin_bundles_detail, admin_add_extra_api,
    admin_bundles_asignar, admin_bundles_liberar, admin_bundles_stats,
    admin_audio_music, admin_audio_music_detail, admin_audio_sfx, admin_audio_sfx_detail,
    admin_apikeys_auto_repair, admin_branding_watermark,
)

router = DefaultRouter()
router.register(r'properties', PropertyViewSet)
router.register(r'assets', GeneratedAssetViewSet)

urlpatterns = [
    path('auth/register/', RegisterView.as_view(), name='auth_register'),
    path('auth/login/', CustomTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('auth/login/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('auth/token/refresh/', TokenRefreshView.as_view(), name='token_refresh_alt'),
    path('auth/logout/', LogoutView.as_view(), name='auth_logout'),
    path('auth/perfil/', PerfilView.as_view(), name='auth_perfil'),
    path('auth/onboarding/', OnboardingView.as_view(), name='auth_onboarding'),
    path('auth/send-otp/', send_otp, name='auth_send_otp'),
    path('auth/verify-otp/', verify_otp, name='auth_verify_otp'),
    path('auth/plan-status/', plan_status, name='plan_status'),
    path('auth/seleccionar-plan-free/', seleccionar_plan_free, name='seleccionar_plan_free'),
    path('recuperar-password/', recuperar_password, name='recuperar_password'),
    path('confirmar-recuperacion/', confirmar_recuperacion, name='confirmar_recuperacion'),
    
    path('dashboard/', views.dashboard, name='dashboard'),
    path('listados/', ListadosView.as_view(), name='listados'),
    path('listados/<int:pk>/', ListadoDetalleView.as_view(), name='listado_detalle'),
    path('listados/upload-fotos/', upload_fotos_listado, name='upload_fotos_listado'),
    path('listados/<int:pk>/html/', generar_html, name='generar_html'),
    path('listados/<int:pk>/generar-video/', generar_video, name='generar_video'),
    path('listados/<int:listado_id>/pdf-proxy/', proxy_pdf_view, name='pdf_proxy'),
    path('listados/<int:listado_id>/pdf-thumbnail/', proxy_pdf_thumbnail_view, name='pdf_thumbnail'),
    path('descargar-pdf/<int:listado_id>/', views.descargar_pdf, name='descargar_pdf'),

    path('', include(router.urls)),
    path('generar-guion/', generar_guion, name='generar_guion'),
    path('generar-escena/', generar_escena, name='generar_escena'),
    path('generar-listado/', generar_listado, name='generar_listado'),
    path('generar-pdf/', generar_pdf, name='generar_pdf'),
    path('generar-imagen-post/', generar_imagen_post, name='generar_imagen_post'),
    path('generar-imagen-story/', generar_imagen_story, name='generar_imagen_story'),
    path('generar-email/', generar_email, name='generar_email'),
    path('publicar-instagram/', publicar_instagram, name='publicar_instagram'),
    path('publicar-redes/', publicar_redes_sociales, name='publicar_redes_sociales'),
    path('pdf/<str:uuid_str>/', serve_pdf_file, name='serve_pdf'),
    path('video-status/<int:listado_id>/', video_status, name='video_status'),
    
    path('mp/checkout/', mp_checkout,  name='mp_checkout'),
    path('mp/webhook/',  mp_webhook,   name='mp_webhook'),
    path('mp/plan/',     get_plan_info_mp,       name='mp_plan_info'),

    # Legal
    path('terminos-y-condiciones/', obtener_terminos, name='obtener_terminos'),
    path('politica-privacidad/', obtener_politica_privacidad, name='obtener_politica_privacidad'),

    # Test endpoints
    path('test-upload/', test_upload_avatar, name='test_upload_avatar'),
    path('generar-carrusel/', generar_carrusel, name='generar_carrusel'),
    path('amenidades-presets/', amenidades_presets, name='amenidades_presets'),

    # Admin Dash
    path('admin/stats/', admin_metricas),
    path('admin/usuarios/', admin_usuarios_list),
    path('admin/usuarios-eliminados/', admin_usuarios_eliminados),
    path('admin/usuarios/<int:user_id>/', admin_usuario_eliminar),
    path('admin/usuarios/<int:user_id>/restaurar/', admin_usuario_restaurar),
    path('admin/usuarios/<int:user_id>/detalle/', admin_usuario_detalle),
    path('admin/usuarios/<int:user_id>/cambiar-plan/', admin_usuario_cambiar_plan),
    path('admin/usuarios/<int:user_id>/suspender/', admin_usuario_suspender),
    path('admin/usuarios/<int:user_id>/email/', admin_enviar_email),
    path('admin/users/<int:user_id>/add-extra/', admin_add_extra_api),
    path('admin/listados/', views.admin_listados),
    path('admin/assets/', views.admin_assets),
    path('admin/pagos/', views.admin_pagos),
    
    # API Keys & Pool
    path('admin/apikeys/resumen/', admin_apikeys_resumen),
    path('admin/apikeys/pool/', admin_apikeys_pool),
    path('admin/apikeys/pool/crear/', admin_apikeys_pool_crear),
    path('admin/apikeys/pool/bulk/', admin_apikeys_pool_bulk),
    path('admin/apikeys/pool/<int:key_id>/', admin_apikeys_pool_detail),
    path('admin/apikeys/pool/<int:key_id>/detalle/', admin_apikeys_pool_detail),
    path('admin/apikeys/global/', admin_apikeys_global),
    path('admin/apikeys/pool/auto-repair/', admin_apikeys_auto_repair),
    path('admin/pool/estado/', admin_pool_estado),
    path('admin/pool/listar/', admin_apikeys_pool), # Alias
    path('admin/alerts/<int:alert_id>/read/', admin_alerts_read),
    path('admin/health-check/', admin_health_check),

    # Conexiones Redes (UploadPost)
    path('conexiones/init/', views.conexiones_init),
    path('conexiones/estado/', views.conexiones_estado),
    path('conexiones/eliminar/', views.conexiones_eliminar),

    # Debug / Diagnóstico
    path('debug/email-check/', views.debug_email_check, name='debug_email_check'),
    path('debug/email-send/',  views.debug_email_send,  name='debug_email_send'),
    path('debug/uploadpost/<str:username>/', views.debug_uploadpost, name='debug_uploadpost'),

    # Uso de APIs
    path('auth/mi-uso/', views_usage.mi_uso_apis, name='mi_uso_apis'),
    path('admin/uso-global/', views_usage.admin_uso_global, name='admin_uso_global'),

    # API Bundles
    path('admin/bundles/', admin_bundles_list),
    path('admin/bundles/crear/', admin_bundles_crear),
    path('admin/bundles/stats/', admin_bundles_stats),
    path('admin/bundles/<int:bundle_id>/', admin_bundles_detail),
    path('admin/bundles/<int:bundle_id>/asignar/', admin_bundles_asignar),
    path('admin/bundles/<int:bundle_id>/liberar/', admin_bundles_liberar),

    # Librería de Audio
    path('admin/audio/music/', admin_audio_music),
    path('admin/audio/music/<int:pk>/', admin_audio_music_detail),
    path('admin/audio/sfx/', admin_audio_sfx),
    path('admin/audio/sfx/<int:pk>/', admin_audio_sfx_detail),
    path('admin/branding/watermark/', admin_branding_watermark),

    # Notificaciones
    path('notificaciones/', views.listar_notificaciones),
    path('notificaciones/<int:notif_id>/leer/', views.marcar_notificacion_leida),
    path('notificaciones/leer-todas/', views.marcar_todas_leidas),
    path('cuota-ia/', views.estado_cuota_ia),
    path('mp/checkout-extra/', views.mp_checkout_api_extra),
    path('debug/quota/', views.debug_quota),
]
```

### File: api/views.py
```python
from rest_framework import viewsets, status
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, AllowAny, IsAdminUser
from rest_framework_simplejwt.tokens import RefreshToken
from django.utils import timezone
from django.db.models import Sum
import requests
from django.http import HttpResponse, StreamingHttpResponse
from decouple import config
import cloudinary
import cloudinary.uploader
from api.services.almacenamiento import AlmacenamientoCloudinary
import logging

logger = logging.getLogger(__name__)

from .models import (
    Property, GeneratedAsset, Listado, OTPCode,
    TerminosCondiciones, PoliticaPrivacidad
)
from .serializers import (
    PropertySerializer, GeneratedAssetSerializer, RegisterSerializer,
    TerminosCondicionesSerializer, PoliticaPrivacidadSerializer
)
from .tasks import run_asset_generation
from .ai_services import call_groq_api, call_gemini_api, smart_call, GeminiQuotaExhaustedError
from .utils import crear_notificacion
from django.template.loader import render_to_string
from .services.render_engine import render_html_to_image
from .plan_utils import puede_generar, incrementar_uso

def actualizar_resultados_listado(listado, tipo, resultado):
    """
    Guarda el resultado (URL, caption, etc) dentro del JSON de datos del listado.
    Esto permite persistencia entre sesiones.
    """
    if not listado: return
    if not isinstance(listado.datos, dict):
        listado.datos = {}
    
    if 'resultados' not in listado.datos:
        listado.datos['resultados'] = {}
    
    listado.datos['resultados'][tipo] = resultado
    listado.save(update_fields=['datos'])

LIMITES_PLAN = {
    'free':     {'listados_mes': 10},
    'starter':  {'listados_mes': 40},
    'pro':      {'listados_mes': 150},
    'scale':    {'listados_mes': 999999},
    'business': {'listados_mes': 999999},
}

def verificar_limite_plan(agent):
    from datetime import datetime
    plan = getattr(agent, 'plan_nombre', 'free')
    limite = LIMITES_PLAN.get(plan, LIMITES_PLAN['free'])
    
    ahora = datetime.now()
    listados_mes = Listado.objects.filter(
        agente=agent,
        creado_en__year=ahora.year,
        creado_en__month=ahora.month
    ).count()
    
    if listados_mes >= limite['listados_mes']:
        return False, listados_mes, limite['listados_mes']
    return True, listados_mes, limite['listados_mes']

from io import BytesIO
from django.template.loader import get_template

from django.http import HttpResponse

import base64
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import io
import tempfile
import uuid
import os
import time

def generar_qr_url(telefono, tipo_propiedad='', ciudad='', operacion='', precio='', moneda=''):
    import urllib.parse, urllib.request, base64
    # Limpiar teléfono: solo dígitos
    tel_limpio = ''.join(filter(str.isdigit, str(telefono)))
    # Si no empieza con código de país, asumir Argentina (+54)
    if tel_limpio and not tel_limpio.startswith('54'):
        tel_limpio = '54' + tel_limpio
    # Armar mensaje profesional
    detalle = f"{tipo_propiedad} en {ciudad}".strip(' en') if tipo_propiedad or ciudad else "propiedad"
    precio_str = f" por {moneda} {precio}" if precio else ""
    op_str = f" en {operacion.lower()}" if operacion else ""
    mensaje = f"Hola! Me interesa {detalle}{op_str}{precio_str}. ¿Podés darme más información?"
    # Armar URL de WhatsApp
    wa_url = f"https://wa.me/{tel_limpio}?text={urllib.parse.quote(mensaje)}"
    # Generar QR de la URL de WhatsApp
    qr_api = f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={urllib.parse.quote(wa_url)}"
    try:
        with urllib.request.urlopen(qr_api, timeout=5) as resp:
            png_bytes = resp.read()
        b64 = base64.b64encode(png_bytes).decode()
        return f"data:image/png;base64,{b64}"
    except Exception as e:
        print(f"[QR] Error: {e}")
        return ''

def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip

from rest_framework_simplejwt.views import TokenObtainPairView
from api.models import BannedIP, Agent

class CustomTokenObtainPairView(TokenObtainPairView):
    def post(self, request, *args, **kwargs):
        ip = get_client_ip(request)
        if BannedIP.objects.filter(ip_address=ip).exists():
            return Response({'detail': 'Tu IP ha sido bloqueada. Contacta al soporte.'}, status=status.HTTP_403_FORBIDDEN)
        
        response = super().post(request, *args, **kwargs)
        if response.status_code == 200:
            # Login successful
            email = request.data.get('email')
            user_agent = request.META.get('HTTP_USER_AGENT', '')
            try:
                agent = Agent.objects.get(email=email)
                agent.last_login_ip = ip
                agent.last_login_user_agent = user_agent
                agent.save(update_fields=['last_login_ip', 'last_login_user_agent'])
            except Agent.DoesNotExist:
                pass
        return response

class RegisterView(APIView):
    permission_classes = [AllowAny]
    def post(self, request):
        from datetime import timedelta
        from django.utils import timezone
        email = request.data.get('email', '').strip().lower()
        
        ip = get_client_ip(request)
        if BannedIP.objects.filter(ip_address=ip).exists():
            return Response({'error': 'Tu IP ha sido bloqueada. No podés crear cuentas.'}, status=status.HTTP_403_FORBIDDEN)
        
        # Verificar blacklist de emails baneados permanentemente
        from .models import Agent, BannedEmail
        if BannedEmail.objects.filter(email=email).exists():
            return Response({"error": "Esta cuenta ha sido inhabilitada permanentemente. No podés registrarte con este email."}, status=403)
        
        # Validar email duplicado
        if Agent.objects.filter(email=email).exists():
            return Response({"error": "Este email ya está registrado. ¿Olvidaste tu contraseña?"}, status=400)

        otp_verificado = OTPCode.objects.filter(
            email=email,
            verified=True,
            created_at__gte=timezone.now() - timedelta(hours=1)
        ).exists()
        if not otp_verificado:
            return Response({"error": "Debés verificar tu email primero"}, status=400)
            
        serializer = RegisterSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            
            # Asignar plan free por defecto
            user.plan_nombre = 'free'
            user.plan_activo = True
            user.plan_seleccionado = True
            user.save()
            
            # TAREA 3: Consumir el OTP para que no pueda reutilizarse
            otp_usado = OTPCode.objects.filter(
                email=email,
                verified=True,
                created_at__gte=timezone.now() - timedelta(hours=1)
            ).order_by('-created_at').first()
            if otp_usado:
                otp_usado.verified = False
                otp_usado.code_hash = 'USED'
                otp_usado.save()

            user.last_login_ip = ip
            user.last_login_user_agent = request.META.get('HTTP_USER_AGENT', '')
            user.save(update_fields=['last_login_ip', 'last_login_user_agent'])
            refresh = RefreshToken.for_user(user)
            return Response({
                'access': str(refresh.access_token),
                'refresh': str(refresh),
            }, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class LogoutView(APIView):
    permission_classes = [IsAuthenticated]
    def post(self, request):
        try:
            refresh_token = request.data["refresh_token"]
            token = RefreshToken(refresh_token)
            token.blacklist()
            return Response(status=status.HTTP_205_RESET_CONTENT)
        except Exception as e:
            return Response(status=status.HTTP_400_BAD_REQUEST)

class PropertyViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    queryset = Property.objects.none()
    serializer_class = PropertySerializer

    def get_queryset(self):
        return Property.objects.filter(agent=self.request.user)

    @action(detail=True, methods=['post'])
    def generate_assets(self, request, pk=None):
        property_instance = self.get_object()
        
        # Trigger Celery Task
        run_asset_generation.delay(property_instance.id)

        return Response({
            'message': 'Asset generation triggered successfully.',
            'status': 'PROCESSING'
        }, status=status.HTTP_202_ACCEPTED)

class GeneratedAssetViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated]
    queryset = GeneratedAsset.objects.none()
    serializer_class = GeneratedAssetSerializer

    def get_queryset(self):
        return GeneratedAsset.objects.filter(agent=self.request.user)
import os
import concurrent.futures

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generar_guion(request):
    # TODO: re-habilitar cuando el sistema de planes esté estable
    # if not puede_generar(request.user, 'ai'):
    #     return Response({
    #         "error": "limite_alcanzado", 
    #         "mensaje": "Superaste el límite de tu plan. Actualizá tu suscripción.",
    #         "upgrade_url": "/precios"
    #     }, status=status.HTTP_403_FORBIDDEN)

    data = request.data
    tipo_video = data.get('tipoVideo', 'reel')
    tipo = data.get('tipoPropiedad', 'Propiedad')
    ciudad = data.get('ciudad', '')
    operacion = data.get('operacion', 'Venta')
    moneda = data.get('moneda', 'USD')
    precio = data.get('precio', '')
    recamaras = str(data.get('recamaras', '') or data.get('habitaciones', ''))
    banos = str(data.get('banos', '') or data.get('bathrooms', ''))
    superficie = str(data.get('superficieCubierta', '') or data.get('metros', ''))
    voz = data.get('voz', 'femenina')          # 'masculina' | 'femenina'
    tono = data.get('tono', 'profesional')     # 'profesional' | 'lujo' | 'energetico'
    voiceover = data.get('voiceover', False)   # bool
    contexto_adicional = data.get('contextoAdicional', '')

    # Mapear tono a instrucciones narrativas
    tono_map = {
        'profesional': 'profesional y formal, directo, transmite confianza y seriedad',
        'lujo':        'de lujo y exclusividad, sofisticado, evoca aspiración y premium lifestyle, usa vocabulario refinado',
        'energetico':  'dinámico y energético, entusiasta, usa frases cortas e impactantes, genera urgencia'
    }
    tono_instrucciones = tono_map.get(tono, tono_map['profesional'])

    # Narrador según voz
    narrador_instrucciones = (
        'con voz masculina en mente: frases firmes, directas, con autoridad'
        if voz == 'masculina' else
        'con voz femenina en mente: frases cálidas, cercanas, invitadoras'
    )

    # Intentar IA solo si hay keys Y con timeout estricto de 5s
    descripcion_ia = None
    GEMINI_KEY = os.environ.get('GEMINI_API_KEY', '')
    GROQ_KEY = os.environ.get('GROQ_API_KEY', '')

    if GEMINI_KEY or GROQ_KEY:
        palabras_por_escena = "25-38 palabras" if tipo_video == 'reel' else "50-75 palabras"
        palabras_total = "100-150 palabras" if tipo_video == 'reel' else "200-300 palabras"
        contexto_extra = f"\nENFOQUE ADICIONAL DEL CLIENTE: {contexto_adicional}" if contexto_adicional else ''
        prompt = f"""Sos un copywriter inmobiliario experto.
Generá un guión PROFESIONAL para video tipo {tipo_video}.

PROPIEDAD:
- Tipo: {tipo}
- Operación: {operacion}
- Ubicación: {ciudad}
- Precio: {moneda} {precio}
- Recámaras: {recamaras}
- Baños: {banos}

ESTILO DE NARRACIÓN:
- Tono: {tono_instrucciones}
- Narrador: {narrador_instrucciones}
- Tipo de video: {tipo_video.upper()} — {'Tour inmersivo y narrado, guía al espectador por la propiedad' if tipo_video == 'tour' else 'Reel dinámico, impacto visual rápido'}{contexto_extra}

REQUISITOS:
- Genera EXACTAMENTE 4 escenas
- Cada escena: {palabras_por_escena} (texto persuasivo y descriptivo)
- Total del guión: {palabras_total}
- Formato: JSON puro

ESTRUCTURA:
[
  {{"nombre":"Apertura","texto":"...","icono":"🏠"}},
  {{"nombre":"Detalles","texto":"...","icono":"✨"}},
  {{"nombre":"Ubicación","texto":"...","icono":"📍"}},
  {{"nombre":"CTA","texto":"...","icono":"📞"}}
]

RESPONDE SOLO JSON, SIN PREAMBLE."""
        try:
            with concurrent.futures.ThreadPoolExecutor() as ex:
                future = ex.submit(call_gemini_api, prompt, agente=request.user)
                descripcion_ia = future.result(timeout=15)
        except Exception:
            descripcion_ia = None

    # Fallback local — siempre 4 escenas con rangos exactos de palabras
    if tipo_video == 'tour':
        # Tour narrado: 6 escenas arquitectónicas (porta el estilo de LEADBOOK UP)
        escenas_default = [
            {"nombre": "Fachada", "icono": "🏠",
             "texto": f"Bienvenidos a esta {tipo} en {operacion} en {ciudad}. Una oportunidad única en el mercado inmobiliario actual. Precio: {moneda} {precio}."},
            {"nombre": "Sala", "icono": "🛋️",
             "texto": "Amplios espacios interiores diseñados para el confort familiar. Luz natural, alturas generosas y un diseño que invita a disfrutar cada rincón."},
            {"nombre": "Cocina", "icono": "🍳",
             "texto": "Cocina funcional con terminaciones de primera calidad, espacios de guardado y distribución inteligente para el uso diario."},
            {"nombre": "Recámara", "icono": "🛏️",
             "texto": f"{'Con ' + str(recamaras) + ' recámaras y ' + str(banos) + ' baños.' if recamaras else 'Dormitorios luminosos para el descanso ideal.'} Acabados de primera línea{(', superficie cubierta de ' + superficie + ' m²') if superficie else ''}."},
            {"nombre": "Exteriores", "icono": "🌿",
             "texto": f"Espacios exteriores que complementan una vida plena en {ciudad}. Zonas de esparcimiento, acceso a servicios y conectividad inmejorable."},
            {"nombre": "Cierre", "icono": "📞",
             "texto": f"Precio: {moneda} {precio}. No dejes que alguien más tome esta decisión. Contactanos hoy mismo y agendá tu visita personalizada. ¡Te esperamos!"}
        ]
    else:  # reel rápido: 100-150 palabras totales (25-38 palabras por escena)
        escenas_default = [
            {"nombre": "Apertura", "icono": "⚡",
             "texto": f"✨ {tipo} en {operacion} en {ciudad}. Precio: {moneda} {precio}. Una oportunidad única en el mercado inmobiliario actual. No te la pierdas."},
            {"nombre": "Características", "icono": "🏠",
             "texto": f"{recamaras} recámaras · {banos} baños{(' · ' + superficie + ' m²') if superficie else ''}. Espacios amplios, luminosos y diseñados para el máximo confort. Acabados de primera categoría."},
            {"nombre": "Ubicación", "icono": "📍",
             "texto": f"Estratégicamente ubicado en {ciudad}. Acceso a los mejores servicios, comercios, transporte y zonas de esparcimiento. Todo lo que necesitás, cerca de vos."},
            {"nombre": "Contacto", "icono": "📞",
             "texto": f"¡El hogar que soñabas está en {ciudad}! Contactanos ahora mismo, agendá tu visita y hacelo tuyo antes de que sea tarde."}
        ]


    # Parsear respuesta de IA si vino bien
    escenas_finales = escenas_default
    if descripcion_ia:
        from .plan_utils import registrar_uso
        registrar_uso(request.user, 'ai')
        try:
            import json as _json
            parsed = _json.loads(descripcion_ia)
            if isinstance(parsed, list) and len(parsed) >= 4:
                escenas_finales = parsed
        except Exception:
            pass

    return Response({'escenas': escenas_finales, 'tipo_video': tipo_video})

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generar_listado(request):
    # TODO: re-habilitar cuando el sistema de planes esté estable
    # if not puede_generar(request.user, 'ai'):
    #     return Response({
    #         "error": "limite_alcanzado", 
    #         "mensaje": "Superaste el límite de tu plan. Actualizá tu suscripción.",
    #         "upgrade_url": "/precios"
    #     }, status=status.HTTP_403_FORBIDDEN)
            
    prompt_text = request.data.get("prompt", "")
    if not prompt_text:
        return Response({"error": "No prompt provided. Please pass a 'prompt' field in the JSON body."}, status=status.HTTP_400_BAD_REQUEST)
        
    system_prompt = "Sos un as copywriter de real estate. Escribí descripciones profesionales, persuasivas y completas (listados) para propiedades en venta o alquiler en español."

    try:
        result = call_groq_api(prompt_text, system_prompt=system_prompt)
    except Exception as e_groq:
        # Fallback: intentar con Gemini si Groq falla
        try:
            result = call_gemini_api(prompt_text, system_prompt=system_prompt, agente=request.user)
        except Exception as e_gem:
            return Response({
                "error": "IA no disponible",
                "detalle": f"Groq: {e_groq} | Gemini: {e_gem}"
            }, status=status.HTTP_503_SERVICE_UNAVAILABLE)

    if request.user.is_authenticated:
        incrementar_uso(request.user, 'ai')
    return Response({"generated_text": result}, status=status.HTTP_200_OK)

class DashboardView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        now = timezone.now()
        start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        
        listados = Listado.objects.filter(agente=user)
        listados_este_mes = listados.filter(creado_en__gte=start_of_month).count()
        total_generados = listados.count()
        
        videos_creados = listados.aggregate(total_videos=Sum('videos_creados'))['total_videos'] or 0

        listados_recientes = listados.order_by('-creado_en')[:5].values(
            'id', 'titulo', 'tipo_propiedad', 'ciudad', 'precio', 'creado_en', 'datos', 'video_url', 'video_status'
        )

        susc = get_suscripcion(user)
        plan = susc.plan

        return Response({
            "nombre_inmobiliaria": getattr(user, 'nombre_inmobiliaria', None),
            "logo_url": getattr(user, 'logo_url', None),
            "listados_este_mes": listados_este_mes,
            "total_generados": total_generados,
            "videos_creados": videos_creados,
            "conexiones_activas": 0,
            "listados_recientes": list(listados_recientes),
            "plan": plan.nombre,
            "plan_limites": {
                "properties_per_month": plan.properties_per_month,
                "ai_generations": plan.ai_generations,
                "image_generations": plan.image_generations,
                "video_generations": plan.video_generations,
                "branding": plan.branding
            },
            "uso_actual": {
                "properties_used": susc.properties_used,
                "ai_used": susc.ai_used,
                "images_used": susc.images_used,
                "videos_used": susc.videos_used
            }
        })

class PerfilView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        return Response({
            "email": user.email,
            "nombre": user.nombre,
            "nombre_inmobiliaria": getattr(user, 'nombre_inmobiliaria', None),
            "agencia": getattr(user, 'agencia', None),
            "logo_url": getattr(user, 'logo_url', None),
            "telefono": getattr(user, 'telefono', None),
            "nicho": getattr(user, 'nicho', None),
            "pais": getattr(user, 'pais', None),
            "nacionalidad": getattr(user, 'nacionalidad', None),
            "sitio_web": getattr(user, 'sitio_web', None),
            "bio": getattr(user, 'bio', None),
            "meta_access_token": getattr(user, 'meta_access_token', None),
            "meta_instagram_account_id": getattr(user, 'meta_instagram_account_id', None),
            "agentes_asociados": getattr(user, 'agentes_asociados', []),
            "plan_nombre": getattr(user, 'plan_nombre', 'starter'),
            "is_staff": user.is_staff,
            "plan_seleccionado": user.plan_seleccionado,
            "plan_activo": user.plan_activo,
        })

    def put(self, request):
        from .models import Agent
        user = Agent.objects.get(id=request.user.id)
        data = request.data
        
        if 'nombre_inmobiliaria' in data:
            user.nombre_inmobiliaria = data['nombre_inmobiliaria']
        elif 'nombreInmobiliaria' in data:
            user.nombre_inmobiliaria = data['nombreInmobiliaria']
            
        if 'logo_url' in data:
            user.logo_url = data['logo_url']
        elif 'logoUrl' in data:
            user.logo_url = data['logoUrl']
            
        agentes_input = data.get('agentes_asociados')
        if agentes_input is None:
            agentes_input = data.get('agentesAsociados')
            
        if agentes_input is not None:
            # Si el frontend envía un string en vez de un array JSON, lo parseamos
            import json
            if isinstance(agentes_input, str):
                try:
                    agentes_input = json.loads(agentes_input)
                except json.JSONDecodeError:
                    pass
            user.agentes_asociados = agentes_input
            
        if 'meta_access_token' in data:
            user.meta_access_token = data['meta_access_token']
        if 'meta_instagram_account_id' in data:
            user.meta_instagram_account_id = data['meta_instagram_account_id']
        if 'telefono' in data:
            user.telefono = data['telefono']
        if 'agencia' in data:
            user.agencia = data['agencia']
        if 'nicho' in data:
            user.nicho = data['nicho']
        if 'pais' in data:
            user.pais = data['pais']
        if 'nacionalidad' in data:
            user.nacionalidad = data['nacionalidad']
        if 'sitio_web' in data:
            user.sitio_web = data['sitio_web']
        if 'bio' in data:
            user.bio = data['bio']
            
        user.save()
        return Response({
            "message": "Perfil actualizado exitosamente",
            "email": user.email,
            "nombre": user.nombre,
            "nombre_inmobiliaria": getattr(user, 'nombre_inmobiliaria', None),
            "agencia": getattr(user, 'agencia', None),
            "logo_url": getattr(user, 'logo_url', None),
            "telefono": getattr(user, 'telefono', None),
            "nicho": getattr(user, 'nicho', None),
            "pais": getattr(user, 'pais', None),
            "nacionalidad": getattr(user, 'nacionalidad', None),
            "sitio_web": getattr(user, 'sitio_web', None),
            "bio": getattr(user, 'bio', None),
            "meta_access_token": getattr(user, 'meta_access_token', None),
            "meta_instagram_account_id": getattr(user, 'meta_instagram_account_id', None),
            "agentes_asociados": getattr(user, 'agentes_asociados', []),
            "plan_nombre": getattr(user, 'plan_nombre', 'starter')
        }, status=status.HTTP_200_OK)

from .services.instagram_service import publicar_post, publicar_story, publicar_carrusel, publicar_media_upload_api
from django.conf import settings

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def publicar_instagram(request):
    try:
        data = request.data
        tipo = data.get('tipo', 'post')
        imagen_url = data.get('imagen_url', '')
        imagenes_urls = data.get('imagenes_urls', [])
        caption = data.get('caption', '')
        
        user = request.user
        access_token = user.meta_access_token or getattr(settings, 'META_ACCESS_TOKEN', '')
        account_id = user.meta_instagram_account_id or getattr(settings, 'META_INSTAGRAM_ACCOUNT_ID', '')
        
        if not access_token or not account_id:
            return Response({"success": False, "error": "Credenciales de Instagram no configuradas."}, status=status.HTTP_400_BAD_REQUEST)
            
        if tipo == 'post':
            result = publicar_post(imagen_url, caption, access_token, account_id)
        elif tipo == 'story':
            result = publicar_story(imagen_url, access_token, account_id)
        elif tipo == 'carrusel':
            result = publicar_carrusel(imagenes_urls, caption, access_token, account_id)
        else:
            return Response({"success": False, "error": "Tipo invalido (post/story/carrusel)"}, status=status.HTTP_400_BAD_REQUEST)
            
        if result.get('success'):
            return Response(result, status=status.HTTP_200_OK)
        else:
            return Response(result, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    except Exception as e:
        return Response({"success": False, "error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def publicar_redes_sociales(request):
    """
    Endpoint unificado para publicar contenido en redes sociales vía Upload Post API.
    Tipos soportados: image, video, carousel, document (PDF).
    """
    try:
        data = request.data
        media_type = data.get('media_type', 'image') # image, video, carousel, document
        caption = data.get('caption', '')
        
        # URLs de contenido
        image_url = data.get('image_url')
        video_url = data.get('video_url')
        document_url = data.get('document_url')
        images = data.get('images', []) # array de URLs para carrusel
        
        # Opciones extra
        platforms = data.get('platforms') # ej: ['instagram', 'facebook', 'youtube']
        scheduled_at = data.get('scheduled_at') # string ISO 8601
        
        user = request.user
        
        # Llamar al servicio unificado de Upload Post
        result = publicar_media_upload_api(
            media_type=media_type,
            caption=caption,
            image_url=image_url,
            video_url=video_url,
            images=images,
            document_url=document_url,
            platforms=platforms,
            scheduled_at=scheduled_at,
            agente=user
        )
        
        if result.get('success'):
            # --- Añadir tracking manual de uso para UploadPost ---
            try:
                from api.pool_manager import get_api_key
                from api.models import APIKey
                from django.utils import timezone
                key_str = get_api_key(user, 'uploadpost')
                if key_str:
                    k = APIKey.objects.filter(api_key=key_str).first()
                    if k:
                        k.requests_today += 1
                        k.requests_this_month += 1
                        k.total_requests += 1
                        k.last_used_at = timezone.now()
                        k.save()
            except Exception as trk_e:
                print(f"[UploadPost Tracking Error]: {trk_e}")
            # -----------------------------------------------------
            
            return Response(result, status=status.HTTP_200_OK)
        else:
            return Response(result, status=status.HTTP_400_BAD_REQUEST)
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        return Response({"success": False, "error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generar_carrusel(request):
    """Genera 5 imágenes de carrusel y un caption con Gemini."""
    try:
        user = request.user
        # TODO: re-habilitar cuando el sistema de planes esté estable
        # if not puede_generar(user, 'image'):
        #      return Response({
        #         "error": "limite_alcanzado", 
        #         "mensaje": "Superaste el límite de tu plan. Actualizá tu suscripción.",
        #         "upgrade_url": "/precios"
        #     }, status=status.HTTP_403_FORBIDDEN)

        data = request.data
        fotos = data.get('fotosRecorrido', [])
        if not isinstance(fotos, list): fotos = []
        
        # Aseguramos tener 5 fotos (repetimos si es necesario)
        portada = data.get('portadaUrl')
        images_to_use = []
        if portada: images_to_use.append(portada)
        images_to_use.extend([f.get('url') if isinstance(f, dict) else f for f in fotos if f])
        
        # Si no hay imágenes, generamos slides de diseño puro (sin foto de fondo)
        # Pasamos None para que generate_social_image use fondo negro/degradado
        if not images_to_use:
            images_to_use = [None] * 5
        
        while len(images_to_use) < 5:
            images_to_use.append(images_to_use[len(images_to_use) % len(images_to_use)])
            
        slides_urls = []
        slides_content = [
            {"headline": data.get('tipoPropiedad', 'Propiedad'), "subheadline": f"Una oportunidad única en {data.get('ciudad', '')}"},
            {"headline": "Espacios", "subheadline": "Diseño y amplitud pensados para tu máximo confort."},
            {"headline": "Detalles", "subheadline": "Terminaciones de calidad que marcan la diferencia."},
            {"headline": "Inversión", "subheadline": f"Tu próximo hogar por solo {data.get('moneda', 'USD')} {data.get('precio', '')}"},
            {"headline": "Contacto", "subheadline": "No dejes pasar esta oportunidad. Contactanos hoy."}
        ]

        for i in range(5):
            # Preparar contexto para el slide actual
            context = {
                "portada_url": images_to_use[i],
                "headline": slides_content[i]["headline"],
                "subheadline": slides_content[i]["subheadline"],
                "slide_number": i + 1,
                "total_slides": 5,
                "logo_url": data.get('logoAgenciaUrl')
            }
            
            # Renderizar el slide con Playwright
            html_content = render_to_string('renders/carousel.html', context)
            image_stream = render_html_to_image(html_content, 1080, 1350)
            
            # Subir a Cloudinary via Almacenamiento centralizado
            try:
                image_stream.seek(0)
                listado_id_val = data.get('listado_id')
                url = AlmacenamientoCloudinary.guardar_slide_carrusel(
                    image_stream, 
                    user_id=request.user.id, 
                    listado_id=listado_id_val,
                    slide_index=i + 1
                )
                if not url:
                    raise Exception('Almacenamiento devolvió None')
                slides_urls.append(url)
            except Exception as cloud_err:
                print(f"[DEBUG] ERROR Almacenamiento Slide {i+1}: {str(cloud_err)}")
                return Response({"error": f"Error subiendo slide {i+1}"}, status=500)

        # Generar Caption con Gemini (con fallback a Groq)
        prompt_text = f"Escribí un caption para un carrusel de Instagram de una propiedad: {data.get('tipoPropiedad', 'Propiedad')} en {data.get('ciudad', '')} por {data.get('precio', '')}. Enfocado en vender el estilo de vida y llamar a la acción. Usá emojis y hashtags."
        caption = smart_call(prompt_text, system_prompt="Sos un experto en marketing inmobiliario digital.", agente=user)

        # PERSISTENCIA: Guardar en el listado
        if listado_id_val:
            from .models import Listado
            listado_obj = Listado.objects.filter(id=listado_id_val, agente=request.user).first()
            actualizar_resultados_listado(listado_obj, 'carrusel', {"slides": slides_urls, "caption": caption})

        if user.is_authenticated:
            incrementar_uso(user, 'image')

        return Response({
            "slides": slides_urls,
            "caption": caption
        }, status=status.HTTP_200_OK)
    except GeminiQuotaExhaustedError as e:
        crear_notificacion(
            request.user,
            'quota_agotada',
            'Alcanzaste el 100% de tu uso de IA',
            'Tus créditos de generación de contenido se agotaron. Se resetean automáticamente a medianoche.'
        )
        return Response({"error": "cuota_ia_agotada", "mensaje": str(e)}, status=status.HTTP_429_TOO_MANY_REQUESTS)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return Response({"error": str(e), "detalle": traceback.format_exc()}, status=500)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def test_upload_avatar(request):
    try:
        file = request.FILES.get('file')
        if not file:
            return Response({'error': 'No file provided'}, status=400)
        url = AlmacenamientoCloudinary.guardar_avatar(file, user_id=request.user.id)
        if not url:
            return Response({'error': 'Error al subir imagen'}, status=500)
        return Response({'url': url})
    except Exception as e:
        return Response({'error': str(e)}, status=500)


class OnboardingView(APIView):
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        return self.put(request)

    def put(self, request):
        user = request.user
        data = request.data
        
        if 'nombre_inmobiliaria' in data:
            user.nombre_inmobiliaria = data['nombre_inmobiliaria']
        elif 'nombreInmobiliaria' in data:
            user.nombre_inmobiliaria = data['nombreInmobiliaria']
            
        if 'logo_url' in data:
            user.logo_url = data['logo_url']
        elif 'logoUrl' in data:
            user.logo_url = data['logoUrl']
            
        if 'nicho' in data:
            user.nicho = data['nicho']
        if 'pais' in data:
            user.pais = data['pais']
            
        if 'telefono' in data:
            user.telefono = data['telefono']
        if 'agencia' in data:
            user.agencia = data['agencia']
        if 'nacionalidad' in data:
            user.nacionalidad = data['nacionalidad']
        if 'sitio_web' in data:
            user.sitio_web = data['sitio_web']
        elif 'sitioWeb' in data:
            user.sitio_web = data['sitioWeb']
        if 'bio' in data:
            user.bio = data['bio']
            
        user.save()
        return Response({
            "email": user.email,
            "nombre": user.nombre,
            "nombre_inmobiliaria": getattr(user, 'nombre_inmobiliaria', None),
            "logo_url": getattr(user, 'logo_url', None),
            "telefono": getattr(user, 'telefono', None),
            "nicho": getattr(user, 'nicho', None),
            "pais": getattr(user, 'pais', None),
            "nacionalidad": getattr(user, 'nacionalidad', None),
            "sitio_web": getattr(user, 'sitio_web', None),
            "bio": getattr(user, 'bio', None),
            "agentes_asociados": getattr(user, 'agentes_asociados', []),
            "plan_nombre": getattr(user, 'plan_nombre', 'starter')
        }, status=status.HTTP_200_OK)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def video_status(request, listado_id):
    try:
        from .models import Listado
        listado = Listado.objects.get(id=listado_id, agente=request.user)
        return Response({
            "status": listado.video_status,
            "video_url": listado.video_url
        }, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({"error": "Listado no encontrado"}, status=status.HTTP_404_NOT_FOUND)

class ListadosView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Devuelve todos los listados del usuario logueado"""
        listados = Listado.objects.filter(agente=request.user)
        data = []
        for listado in listados:
            data.append({
                'id': listado.id,
                'titulo': listado.titulo,
                'tipo_propiedad': listado.tipo_propiedad,
                'ciudad': listado.ciudad,
                'precio': listado.precio,
                'creado_en': listado.creado_en,
                'videos_creados': listado.videos_creados,
                'video_url': listado.video_url,
                'video_status': listado.video_status,
                'datos': listado.datos
            })
        return Response(data)

    def post(self, request):
        from .models import Agent
        user = Agent.objects.get(id=request.user.id)
        
        # TODO: re-habilitar cuando el sistema de planes esté estable
        # puede, usados, maximo = verificar_limite_plan(user)
        # if not puede:
        #     return Response({
        #         "error": f"Alcanzaste el límite de tu plan ({usados}/{maximo} listados este mes). Actualizá tu plan para continuar.",
        #         "limite_alcanzado": True,
        #         "usados": usados,
        #         "maximo": maximo
        #     }, status=403)
            
        data = request.data
        
        # Permitir tanto JSON plano como objeto anidado 'formData' (React)
        payload = data.get('formData') if isinstance(data, dict) and 'formData' in data else data
        if not isinstance(payload, dict):
            payload = {}
            
        # TODO: re-habilitar cuando el sistema de planes esté estable
        # if not puede_generar(user, 'property'):
        #     return Response({"error": "limite_alcanzado", "mensaje": "Superaste el límite de tu plan. Actualizá tu suscripción."}, status=status.HTTP_403_FORBIDDEN)
        
        titulo = payload.get('titulo') or f"Propiedad en {payload.get('ciudad', 'Desconocida')}"
        tipo_propiedad = payload.get('tipoPropiedad', payload.get('tipo_propiedad', ''))
        ciudad = payload.get('ciudad', '')
        precio = str(payload.get('precio', ''))
        
        # Guardamos en datos el payload limpio
        listado = Listado.objects.create(
            agente=user,
            titulo=titulo,
            tipo_propiedad=tipo_propiedad,
            ciudad=ciudad,
            precio=precio,
            datos=payload
        )
        
        incrementar_uso(user, 'property')
        
        return Response({
            "mensaje": "Listado guardado", 
            "id": listado.id,
            "titulo": listado.titulo
        }, status=status.HTTP_201_CREATED)

class ListadoDetalleView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        try:
            listado = Listado.objects.get(pk=pk, agente=request.user)
            return Response({
                "id": listado.id,
                "titulo": listado.titulo,
                "tipo_propiedad": listado.tipo_propiedad,
                "ciudad": listado.ciudad,
                "precio": listado.precio,
                "video_url": listado.video_url,
                "video_status": listado.video_status,
                "datos": listado.datos
            }, status=status.HTTP_200_OK)
        except Listado.DoesNotExist:
            return Response({"error": "Listado no encontrado"}, status=status.HTTP_404_NOT_FOUND)

    def delete(self, request, pk):
        try:
            listado = Listado.objects.get(pk=pk)
        except Listado.DoesNotExist:
            return Response({"error": "Listado no encontrado"}, status=status.HTTP_404_NOT_FOUND)

        if listado.agente.id != request.user.id:
            return Response({"error": "No tienes permiso para eliminar este listado"}, status=status.HTTP_403_FORBIDDEN)

        # ── Eliminar assets de Cloudinary antes de borrar el registro ─────────
        datos = listado.datos or {}
        public_ids_a_eliminar = []  # [(public_id, resource_type, cloud_name, api_key, api_secret)]

        def _extraer_public_id(obj):
            """Extrae public_id y credenciales de un dict de asset de Cloudinary."""
            if isinstance(obj, dict) and obj.get('public_id'):
                return (
                    obj['public_id'],
                    obj.get('resource_type', 'image'),
                    obj.get('cloudinary_account') or obj.get('cloud_name'),
                    obj.get('api_key'),
                    obj.get('api_secret'),
                )
            return None

        # Portada
        portada = datos.get('portadaUrl') or datos.get('portada_url')
        ref = _extraer_public_id(portada)
        if ref:
            public_ids_a_eliminar.append(ref)

        # Fotos de galería
        for foto in (datos.get('fotosRecorrido') or datos.get('fotos_recorrido') or []):
            ref = _extraer_public_id(foto)
            if ref:
                public_ids_a_eliminar.append(ref)

        # Assets generados en resultados
        resultados = datos.get('resultados') or {}
        for key, val in resultados.items():
            if isinstance(val, dict):
                ref = _extraer_public_id(val)
                if ref:
                    public_ids_a_eliminar.append(ref)
                # Slides de carrusel
                for slide in (val.get('slides') or []):
                    ref = _extraer_public_id(slide)
                    if ref:
                        public_ids_a_eliminar.append(ref)
            elif isinstance(val, list):
                for item in val:
                    ref = _extraer_public_id(item)
                    if ref:
                        public_ids_a_eliminar.append(ref)

        # Eliminar en Cloudinary — fallo individual no interrumpe la operación
        import cloudinary
        import cloudinary.uploader
        from api.services.almacenamiento import AlmacenamientoCloudinary
        from django.conf import settings

        for (pub_id, res_type, cloud_name, api_key_val, api_secret_val) in public_ids_a_eliminar:
            try:
                # Usar credenciales del asset si las tiene, sino la cuenta global
                if cloud_name and api_key_val and api_secret_val:
                    cld_cfg = cloudinary.Config(
                        cloud_name=cloud_name,
                        api_key=api_key_val,
                        api_secret=api_secret_val,
                    )
                    cloudinary.uploader.destroy(pub_id, resource_type=res_type, config=cld_cfg)
                else:
                    cloudinary.uploader.destroy(pub_id, resource_type=res_type)
                logger.info(f"[Eliminar] Asset Cloudinary eliminado: {pub_id}")
            except Exception as cld_err:
                logger.warning(f"[Eliminar] No se pudo eliminar asset {pub_id} de Cloudinary: {cld_err}")

        # ── Borrar el registro de PostgreSQL ──────────────────────────────────
        listado.delete()
        return Response({"mensaje": "Listado eliminado"}, status=status.HTTP_200_OK)


    def put(self, request, pk):
        try:
            listado = Listado.objects.get(pk=pk)
        except Listado.DoesNotExist:
            return Response({"error": "Listado no encontrado"}, status=status.HTTP_404_NOT_FOUND)
            
        if listado.agente.id != request.user.id:
            return Response({"error": "No tienes permiso para modificar este listado"}, status=status.HTTP_403_FORBIDDEN)
            
        data = request.data
        if 'datos' in data:
            listado.datos = data['datos']
        if 'video_url' in data:
            listado.video_url = data['video_url']
        if 'video_status' in data:
            listado.video_status = data['video_status']
        
        listado.save()
        return Response({"mensaje": "Listado actualizado"}, status=status.HTTP_200_OK)


# ---- Celery task + endpoint para generación de video ----
from celery import shared_task
from .services.video_service import generar_video_listado

@shared_task
def generar_video_task(listado_id):
    """Genera video con Remotion para el listado"""
    try:
        success = generar_video_listado(listado_id)
        if success:
            from .models import Listado
            from .plan_utils import registrar_uso
            listado = Listado.objects.get(id=listado_id)
            registrar_uso(listado.agente, 'video')
            return {"status": "completado", "id": listado_id}
        else:
            return {"status": "fallido", "id": listado_id}
    except Exception as e:
        return {"error": str(e)}


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generar_video(request, pk):
    """Dispara la generación de video asincronamente"""
    try:
        listado = Listado.objects.get(id=pk, agente=request.user)
        # Dispara tarea Celery
        generar_video_task.delay(pk)
        return Response({
            "status": "generando",
            "mensaje": "El video se está generando en segundo plano",
            "id": pk
        })
    except Listado.DoesNotExist:
        return Response({"error": "Listado no encontrado"}, status=404)

def construir_contexto_pdf(data, user, request=None):
    # ─── Extraer hint de listado para el almacenamiento ──────────────────────
    listado_id_hint  = data.get('listado_id') or data.get('listadoId')

    # ─── Helpers de imágenes para WeasyPrint ─────────────────────────────
    temp_files = []

    def resolver_imagen(val, tipo='portada', indice=0):
        if not val: return None
        
        if isinstance(val, dict) and 'public_id' in val:
            from api.services.almacenamiento import AlmacenamientoCloudinary
            return AlmacenamientoCloudinary.obtener_url_foto(val)
            
        if isinstance(val, str):
            if val.startswith('http'):
                return val
            if val.startswith('data:'):
                from api.services.almacenamiento import AlmacenamientoCloudinary
                try:
                    res = AlmacenamientoCloudinary.guardar_foto_propiedad(
                        base64_str=val,
                        user_id=user.id,
                        listado_id=listado_id_hint,
                        tipo_foto=tipo,
                        indice=indice
                    )
                    if res and 'public_id' in res:
                        return AlmacenamientoCloudinary.obtener_url_foto(res)
                except Exception as e:
                    logger.error(f"Error subiendo base64 en resolver_imagen: {e}")
                return None
                
        return None



    # ─── Extraer campos normalizados ──────────────────────────────────────
    tipo_propiedad   = data.get('tipoPropiedad', data.get('tipo_propiedad', 'Propiedad'))
    ciudad           = data.get('ciudad', '')
    precio           = str(data.get('precio', ''))
    moneda           = data.get('moneda', 'USD')
    operacion        = data.get('operacion', 'Venta')
    recamaras        = data.get('recamaras', '')
    banos            = data.get('banos', '')
    superficie_cubierta = data.get('superficieCubierta', data.get('superficieConstruida', ''))
    superficie_total = data.get('superficieTotal', data.get('superficieTerreno', ''))
    estacionamientos = data.get('estacionamientos', '')
    amenidades       = data.get('amenidades', [])
    if not isinstance(amenidades, list):
        amenidades = []

    # Datos de agente / agencia
    agente_nombre = data.get('agenteNombre', '') or user.nombre or ''
    agente_email = data.get('agenteEmail', '') or user.email or ''
    agencia_nombre = data.get('agenciaNombre', '') or user.nombre_inmobiliaria or 'LeadBook'
    agente_telefono = data.get('agenteTelefono', '') or user.telefono or ''

    # ─── Procesar imágenes (base64 Y URLs) ───────────────────────────────
    logo_val_raw = data.get('logoAgenciaUrl', data.get('logo_url', ''))
    logo_url = resolver_imagen(logo_val_raw)

    portada_val_raw = data.get('portadaUrl', '')
    fotos_raw = data.get('fotosRecorrido', [])

    fotos_limpias = []
    for f in fotos_raw:
        if isinstance(f, dict):
            if f.get('public_id') and f != logo_val_raw:
                fotos_limpias.append(f)
        elif isinstance(f, str) and f and f != logo_val_raw:
            fotos_limpias.append(f)

    # Si la portada viene vacía o es igual al logo, usar la primera foto real de la propiedad
    if not portada_val_raw or portada_val_raw == logo_val_raw:
        if fotos_limpias:
            portada_val_raw = fotos_limpias[0]

    portada_url = resolver_imagen(portada_val_raw)

    fotos_recorrido_urls = []
    for fv in fotos_limpias:
        url_firma = resolver_imagen(fv)
        if url_firma:
            fotos_recorrido_urls.append(url_firma)

    # ─── Procesar escenas si las hay ─────────────────────────────────────
    escenas = data.get('escenas', [])
    if isinstance(escenas, list):
        escenas_procesadas = []
        for escena in escenas:
            if isinstance(escena, dict) and escena.get('fotoUrl'):
                url_firma = resolver_imagen(escena['fotoUrl'])
                escena = {**escena, 'fotoUrl': url_firma or escena['fotoUrl']}
            escenas_procesadas.append(escena)
        data['escenas'] = escenas_procesadas

    # ─── Descripción IA (si no viene en el payload) ──────────────────────
    descripcion = data.get('descripcion', '')
    if not descripcion:
        amenidades_str = ', '.join(amenidades) if amenidades else 'no especificadas'
        prompt_desc = f"""Generá una descripción inmobiliaria profesional de 2 párrafos para:
{tipo_propiedad} en {operacion} en {ciudad}.
Precio: {moneda} {precio}.
Recámaras: {recamaras}. Baños: {banos}.
Superficie construida: {superficie_cubierta}m2.
Terreno: {superficie_total}m2.
Amenidades: {amenidades_str}.

Párrafo 1: Descripción general de la propiedad y ubicación (3-4 oraciones).
Párrafo 2: Destacar amenidades y estilo de vida que ofrece (3-4 oraciones).
Tono elegante y persuasivo. Solo los 2 párrafos, sin títulos ni bullets."""
        descripcion = smart_call(prompt_desc, system_prompt="Sos un copywriter inmobiliario de lujo. Escribís en español, con tono sofisticado y persuasivo.", agente=user)
        if descripcion:
            from .plan_utils import registrar_uso
            registrar_uso(user, 'ai')
        if not descripcion:
            raise GeminiQuotaExhaustedError("Límite diario de IA alcanzado. Intentá de nuevo mañana.")


    # QR Code del agente
    qr_base64_ = generar_qr_url(
        telefono=agente_telefono,
        tipo_propiedad=tipo_propiedad,
        ciudad=ciudad,
        operacion=operacion,
        precio=precio,
        moneda=moneda
    )

    # ─── Construir contexto del template ─────────────────────────────────
    context = {
        'tipo_propiedad':     tipo_propiedad,
        'ciudad':             ciudad,
        'precio':             precio,
        'moneda':             moneda,
        'operacion':          operacion,
        'recamaras':          recamaras,
        'banos':              banos,
        'superficie_cubierta': superficie_cubierta,
        'superficie_total':   superficie_total,
        'estacionamientos':   estacionamientos,
        'descripcion':        descripcion,
        'amenidades':         amenidades,
        'portada_url':        portada_url or '',
        'fotos_recorrido':    fotos_recorrido_urls,
        'logo_url':           logo_url or '',
        'portada_url_raw':    portada_url or '',
        'fotos_recorrido_raw': fotos_recorrido_urls,
        'logo_url_raw':       logo_url or '',
        'agente_nombre':      agente_nombre,
        'agente_telefono':    agente_telefono,
        'agente_email':       agente_email,
        'agencia_nombre':     agencia_nombre,
        'qr_code':            qr_base64_,
    }


    return context, temp_files, listado_id_hint, tipo_propiedad, ciudad

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generar_pdf(request):
    # TODO: re-habilitar cuando el sistema de planes esté estable
    # if not puede_generar(request.user, 'property'):
    #     return Response({
    #         "error": "limite_alcanzado",
    #         "mensaje": "Superaste el límite de tu plan. Actualizá tu suscripción.",
    #         "upgrade_url": "/precios"
    #     }, status=status.HTTP_403_FORBIDDEN)

    try:
        data = request.data.copy() if hasattr(request.data, 'copy') else dict(request.data)
        
        print(f"[PAYLOAD] portadaUrl tipo: {type(data.get('portadaUrl')).__name__} | valor: {str(data.get('portadaUrl', ''))[:80]}")
        print(f"[PAYLOAD] fotosRecorrido tipo: {type(data.get('fotosRecorrido')).__name__} | largo: {len(data.get('fotosRecorrido', []))}")
        if data.get('fotosRecorrido'):
            primera = data['fotosRecorrido'][0]
            print(f"[PAYLOAD] primera foto tipo: {type(primera).__name__} | valor: {str(primera)[:80]}")

        context, temp_files, listado_id_hint, tipo_propiedad, ciudad = construir_contexto_pdf(data, request.user, request)

        print(f"\n[PDF] Generando para {tipo_propiedad} en {ciudad} | portada: {bool(context.get('portada_url'))} | fotos: {len(context.get('fotos_recorrido', []))} | QR: sí")

        from django.template.loader import render_to_string
        from django.http import HttpResponse
        from api.services.render_engine import render_html_to_pdf
        from api.services.almacenamiento import AlmacenamientoCloudinary
        from api.ai_services import generar_html_gemini, generar_html_desde_template
        from .models import Listado

        context['listado_id'] = listado_id_hint

        try:
            html_string = generar_html_desde_template(context, request.user)
        except Exception as e:
            print(f"[PDF] Error en sistema de templates: {e}. Usando fallback Gemini.")
            html_string = generar_html_gemini(context, request.user)
            
        if not html_string:
            print("[PDF] Fallback: Gemini falló, usando render_to_string estático")
            html_string = render_to_string('pdf/property_brochure_html.html', context)

        # ─── Conversión a PDF Real con Playwright ────────────────────────────
        pdf_url = None
        try:
            print(f"[PDF] Iniciando conversión Playwright para listado {listado_id_hint}...")
            pdf_bytes = render_html_to_pdf(html_string)
            if pdf_bytes:
                print(f"[PDF] Conversión exitosa ({len(pdf_bytes)} bytes). Subiendo a Cloudinary...")
                pdf_url = AlmacenamientoCloudinary.guardar_pdf(
                    pdf_bytes, 
                    user_id=request.user.id, 
                    listado_id=listado_id_hint
                )
                
                # Persistir la URL en el listado para el historial
                if listado_id_hint and pdf_url:
                    try:
                        listado = Listado.objects.get(id=listado_id_hint)
                        if not listado.datos: listado.datos = {}
                        if 'resultados' not in listado.datos: listado.datos['resultados'] = {}
                        
                        # Guardamos ambos para que el frontend tenga fallback
                        listado.datos['resultados']['pdf'] = {
                            "html": html_string,
                            "url": pdf_url
                        }
                        listado.save()
                        print(f"[PDF] URL guardada en DB: {pdf_url}")
                    except Listado.DoesNotExist:
                        pass
            else:
                print("[PDF] Error: Playwright devolvió bytes vacíos.")
        except Exception as pdf_err:
            print(f"[PDF ERROR] Falló la conversión/subida: {pdf_err}")
            # El fallback es seguir adelante con el HTML solo

        # ─── Limpiar archivos temporales de imágenes ─────────────────────────
        for f in temp_files:
            try:
                if os.path.exists(f):
                    os.remove(f)
            except Exception:
                pass

        # Devolvemos JSON para que el frontend maneje el preview y el link de descarga
        return Response({
            "html": html_string,
            "url": pdf_url,
            "listado_id": listado_id_hint
        }, status=status.HTTP_200_OK)

    except GeminiQuotaExhaustedError as e:
        from .models import UserAPIQuota
        quota, _ = UserAPIQuota.objects.get_or_create(
            user=request.user, service='gemini',
            defaults={'daily_limit': 1500, 'monthly_limit': 1500}
        )
        quota.is_blocked = True
        quota.requests_today = quota.daily_limit
        quota.save()
        crear_notificacion(
            request.user,
            'quota_agotada',
            'Alcanzaste el 100% de tu uso de IA',
            'Tus créditos de generación de contenido se agotaron. Se resetean automáticamente a medianoche.'
        )
        return Response({
            "error": "cuota_ia_agotada",
            "mensaje": str(e),
        }, status=status.HTTP_429_TOO_MANY_REQUESTS)

    except Exception as e:
        import traceback
        error_completo = traceback.format_exc()
        print(f"[PDF ERROR COMPLETO]\n{error_completo}")
        return Response({"error": str(e), "trace": error_completo}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generar_imagen_post(request):
    """Genera imagen POST y la sube a Cloudinary"""
    try:
        # TODO: re-habilitar cuando el sistema de planes esté estable
        # if not puede_generar(request.user, 'image'):
        #     return Response({
        #         "error": "limite_alcanzado", 
        #         "mensaje": "Superaste el límite de tu plan. Actualizá tu suscripción.",
        #         "upgrade_url": "/precios"
        #     }, status=status.HTTP_403_FORBIDDEN)

        data = request.data
        
        print(f"[POST DEBUG] agenteNombre: {data.get('agenteNombre')}")
        print(f"[POST DEBUG] agenteTelefono: {data.get('agenteTelefono')}")
        print(f"[POST DEBUG] agenciaNombre: {data.get('agenciaNombre')}")
        print(f"[POST DEBUG] keys recibidas: {list(data.keys())}")

        # Preparar contexto para la plantilla premium
        context = {
            "portada_url": data.get('portadaUrl'),
            "operacion": data.get('operacion', 'Venta'),
            "tipoPropiedad": data.get('tipoPropiedad', 'Propiedad'),
            "ciudad": data.get('ciudad', ''),
            "precio": data.get('precio', ''),
            "moneda": data.get('moneda', 'USD'),
            "titulo": f"{data.get('tipoPropiedad', '')} en {data.get('ciudad', '')}",
            "agente_email": data.get('agenteEmail', '') or data.get('agente_email', ''),
            "logo_url": data.get('logoAgenciaUrl'),
            "caracteristicas": [
                {"label": "m²", "valor": data.get('superficieCubierta') or data.get('superficieTotal')},
                {"label": "Hab", "valor": data.get('recamaras')},
                {"label": "Baños", "valor": data.get('banos')},
            ],
            "agente_nombre": data.get('agenteNombre', ''),
            "agente_telefono": data.get('agenteTelefono', ''),
            "agencia_nombre": data.get('agenciaNombre', '') or data.get('agencia_nombre', ''),
            "qr_url": generar_qr_url(
                telefono=data.get('agenteTelefono', ''),
                tipo_propiedad=data.get('tipoPropiedad', ''),
                ciudad=data.get('ciudad', ''),
                operacion=data.get('operacion', ''),
                precio=data.get('precio', ''),
                moneda=data.get('moneda', '')
            ),
        }
        
        fotos_raw = data.get('fotosRecorrido', [])
        portada_val = fotos_raw[0] if fotos_raw else data.get('portadaUrl', '')
        if isinstance(portada_val, dict) and 'public_id' in portada_val:
            cloud = portada_val.get('cloudinary_account', 'df1vldrhb')
            pid = portada_val.get('public_id', '')
            portada_post = f"https://res.cloudinary.com/{cloud}/image/upload/{pid}"
        else:
            portada_post = str(portada_val) if portada_val else ''
            
        context["portada_url"] = portada_post
        context["caracteristicas"] = [c for c in context["caracteristicas"] if c["valor"]]

        # Renderizar HTML y luego convertir a imagen PNG con Playwright
        TEMPLATES_POST = [
            'renders/post_dubai_night.html',
            'renders/post_beverly_hills.html',
            'renders/post_manhattan.html',
            'renders/post_mediterraneo.html',
            'renders/post_tech_modern.html',
        ]
        template_post = None
        listado_id_val = data.get('listado_id')
        if listado_id_val:
            try:
                from .models import Listado
                listado = Listado.objects.filter(id=listado_id_val).first()
                if listado and listado.datos:
                    template_nombre = listado.datos.get('template', '')
                    if template_nombre:
                        template_post = f'renders/post_{template_nombre}.html'
                        print(f"[POST] Template leído de DB: {template_post}")
            except Exception as e:
                print(f"[POST] Error leyendo template: {e}")

        if not template_post:
            import random
            template_post = random.choice(TEMPLATES_POST)
            print(f"[POST] Template elegido al azar (fallback): {template_post}")
        html_content = render_to_string(template_post, context)
        print(f"[POST] Template elegido: {template_post}")
        image_stream = render_html_to_image(html_content, 1080, 1350)

        # Generar caption con IA (con fallback)
        prompt_text = f"Escribí un caption para Instagram sobre esta propiedad en {data.get('operacion', 'venta')}: {data.get('tipoPropiedad', 'Propiedad')} en {data.get('ciudad', '')} por {data.get('precio', '')}. Máximo 2200 caracteres, usá hashtags y emojis."
        caption = smart_call(prompt_text, system_prompt="Sos un experto en marketing inmobiliario para redes sociales.", agente=request.user)

        # Intentar subir a Cloudinary via Almacenamiento
        try:
            image_stream.seek(0)
            listado_id_val = data.get('listado_id')
            img_url = AlmacenamientoCloudinary.guardar_post(
                image_stream, user_id=request.user.id, listado_id=listado_id_val
            )
            if not img_url:
                raise Exception("Cloudinary no devolvió una URL válida")
            public_id = img_url
        except Exception as cloud_err:
            print(f"[Cloudinary] Error crítico subiendo imagen: {cloud_err}")
            return Response({
                "error": "error_subida",
                "mensaje": "No se pudo subir la imagen a la nube. Reintentá en unos segundos."
            }, status=500)

        # PERSISTENCIA: Guardar en el listado
        if listado_id_val:
            from .models import Listado
            listado_obj = Listado.objects.filter(id=listado_id_val, agente=request.user).first()
            actualizar_resultados_listado(listado_obj, 'post', {"url": img_url, "caption": caption})

        if request.user.is_authenticated:
            incrementar_uso(request.user, 'image')
            from .plan_utils import registrar_uso
            registrar_uso(request.user, 'image')

        return Response({
            "url": img_url,
            "public_id": public_id,
            "caption": caption,
            "texto": caption
        }, status=status.HTTP_200_OK)
    except GeminiQuotaExhaustedError as e:
        from .models import UserAPIQuota
        quota, _ = UserAPIQuota.objects.get_or_create(
            user=request.user, service='gemini',
            defaults={'daily_limit': 1500, 'monthly_limit': 1500}
        )
        quota.is_blocked = True
        quota.requests_today = quota.daily_limit
        quota.save()
        return Response({"error": "cuota_ia_agotada", "mensaje": str(e)}, status=status.HTTP_429_TOO_MANY_REQUESTS)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return Response({"error": str(e), "detalle": traceback.format_exc()}, status=500)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generar_imagen_story(request):
    """Genera imagen Story, la sube a Cloudinary y devuelve también Base64 como respaldo"""
    try:
        # TODO: re-habilitar cuando el sistema de planes esté estable
        # if not puede_generar(request.user, 'image'):
        #     return Response({
        #         "error": "limite_alcanzado",
        #         "mensaje": "Superaste el límite de tu plan. Actualizá tu suscripción.",
        #         "upgrade_url": "/precios"
        #     }, status=status.HTTP_403_FORBIDDEN)

        data = request.data
        
        # Preparar contexto para la plantilla premium
        context = {
            "portada_url": data.get('portadaUrl'),
            "operacion": data.get('operacion', 'Venta'),
            "tipoPropiedad": data.get('tipoPropiedad', 'Propiedad'),
            "ciudad": data.get('ciudad', ''),
            "precio": data.get('precio', ''),
            "moneda": data.get('moneda', 'USD'),
            "logo_url": data.get('logoAgenciaUrl'),
            "caracteristicas": [
                {"label": "m²", "valor": data.get('superficieCubierta') or data.get('superficieTotal')},
                {"label": "Hab", "valor": data.get('recamaras')},
                {"label": "Baños", "valor": data.get('banos')},
            ]
        }
        context["caracteristicas"] = [c for c in context["caracteristicas"] if c["valor"]]

        # Renderizar HTML y luego convertir a imagen PNG con Playwright (Formato vertical 9:16)
        html_content = render_to_string('renders/story.html', context)
        image_stream = render_html_to_image(html_content, 1080, 1920)

        prompt_text = f"Escribí un texto para Instagram Story sobre esta propiedad en {data.get('operacion', 'venta')}: {data.get('tipoPropiedad', 'Propiedad')} en {data.get('ciudad', '')} por {data.get('precio', '')}. Máximo 500 caracteres, enfocado en llamar la atención rápido."
        caption = smart_call(prompt_text, system_prompt="Sos un experto en marketing inmobiliario para redes sociales.", agente=request.user)

        # Intentar subir a Cloudinary via Almacenamiento
        try:
            image_stream.seek(0)
            listado_id_val = data.get('listado_id')
            img_url = AlmacenamientoCloudinary.guardar_story(
                image_stream, user_id=request.user.id, listado_id=listado_id_val
            )
            if not img_url:
                raise Exception("Cloudinary no devolvió una URL válida")
        except Exception as cloud_err:
            print(f"[Cloudinary] Error crítico subiendo story: {cloud_err}")
            return Response({
                "error": "error_subida",
                "mensaje": "No se pudo subir la historia a la nube."
            }, status=500)

        # PERSISTENCIA: Guardar en el listado
        if listado_id_val:
            from .models import Listado
            listado_obj = Listado.objects.filter(id=listado_id_val, agente=request.user).first()
            actualizar_resultados_listado(listado_obj, 'story', {"url": img_url, "caption": caption})

        if request.user.is_authenticated:
            incrementar_uso(request.user, 'image')
            from .plan_utils import registrar_uso
            registrar_uso(request.user, 'image')

        return Response({
            "url": img_url,
            "img_base64": img_base64,
            "public_id": public_id,
            "caption": caption,
            "texto": caption
        }, status=status.HTTP_200_OK)
    except GeminiQuotaExhaustedError as e:
        return Response({"error": "cuota_ia_agotada", "mensaje": str(e)}, status=status.HTTP_429_TOO_MANY_REQUESTS)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return Response({"error": str(e), "detalle": traceback.format_exc()}, status=500)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generar_email(request):
    try:
        # TODO: re-habilitar cuando el sistema de planes esté estable
        # if not puede_generar(request.user, 'ai'):
        #     return Response({
        #         "error": "limite_alcanzado", 
        #         "mensaje": "Superaste el límite de tu plan. Actualizá tu suscripción.",
        #         "upgrade_url": "/precios"
        #     }, status=status.HTTP_403_FORBIDDEN)
            
        data = request.data.copy() if hasattr(request.data, 'copy') else dict(request.data)
        
        prompt_text = f"""
Redacta el cuerpo de un email profesional para ofrecer esta propiedad a un cliente interesado.
Tipo: {data.get('tipoPropiedad', 'Propiedad')}
Ciudad: {data.get('ciudad', '')}
Precio: {data.get('precio', '')}
Operación: {data.get('operacion', 'venta')}
Agente: {data.get('agenteNombre', '')}
Agencia: {data.get('agenciaNombre', '')}

Devuelve **ÚNICAMENTE** y estrictamente un objeto JSON válido (sin Markdown, sin ````json) con la siguiente estructura y nada más:
{{
  "asunto": "el asunto sugerido del correo",
  "html": "el cuerpo del email en una línea, todo en codigo html inline, usando etiquetas como <br>, <strong> (sin los tags <html>, <head> o <body>, solo contenido directo)",
  "texto_plano": "el equivalente en texto plano básico pero atractivo"
}}
"""
        json_str = smart_call(prompt_text, system_prompt="Sos un asistente técnico que solo responde en JSON.", agente=request.user)
        
        if json_str is None:
            json_str = '{"asunto": "Propiedad destacada", "html": "<div>Tenemos una excelente oportunidad para vos. Contestá a este mail para más detalles.</div>", "texto_plano": "Tenemos una excelente oportunidad para vos. Contestá a este mail para más detalles."}'
            
        import json
        try:
            parsed = json.loads(json_str)
        except:
            if '```json' in json_str:
                json_str = json_str.split('```json')[1].split('```')[0].strip()
                parsed = json.loads(json_str)
            else:
                parsed = {
                    "asunto": "Propiedad destacada",
                    "html": "<div>Propiedad disponible</div>",
                    "texto_plano": "Propiedad disponible"
                }
                
        if request.user.is_authenticated:
            incrementar_uso(request.user, 'ai')

        # Inyectar en plantilla premium para que no sea solo texto pelado
        context = {
            "asunto": parsed.get("asunto", "Propiedad destacada"),
            "tipoPropiedad": data.get('tipoPropiedad', 'Propiedad'),
            "ciudad": data.get('ciudad', ''),
            "precio": data.get('precio', ''),
            "moneda": data.get('moneda', 'USD'),
            "operacion": data.get('operacion', 'Venta'),
            "agenteNombre": data.get('agenteNombre', request.user.first_name if request.user.first_name else request.user.username),
            "agenciaNombre": data.get('agenciaNombre', ''),
            "portada_url": data.get('portadaUrl'),
            "logo_url": data.get('logoAgenciaUrl'),
            "html_content": parsed.get("html", "")
        }
        premium_html = render_to_string('emails/marketing.html', context)
        parsed["html"] = premium_html
        
        # PERSISTENCIA: Guardar en el listado
        listado_id_val = data.get('listado_id') or data.get('listadoId')
        if listado_id_val:
            from .models import Listado
            listado_obj = Listado.objects.filter(id=listado_id_val, agente=request.user).first()
            actualizar_resultados_listado(listado_obj, 'email', parsed)
            
        return Response(parsed, status=status.HTTP_200_OK)
    except GeminiQuotaExhaustedError as e:
        return Response({"error": "cuota_ia_agotada", "mensaje": str(e)}, status=status.HTTP_429_TOO_MANY_REQUESTS)
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@permission_classes([AllowAny])
def serve_pdf_file(request, uuid_str):
    """Sirve el PDF generado. Soporta ambos prefijos (lb_pdf_ y pdf_) para compatibilidad."""
    from django.http import FileResponse
    # Buscar con nuevo prefijo primero, luego el legacy
    for prefix in ['lb_pdf_', 'pdf_']:
        pdf_path = os.path.join(tempfile.gettempdir(), f"{prefix}{uuid_str}.pdf")
        if os.path.exists(pdf_path):
            response = FileResponse(open(pdf_path, 'rb'), content_type='application/pdf')
            response['Content-Disposition'] = 'inline; filename="ficha-leadbook.pdf"'
            response['X-Frame-Options'] = 'ALLOWALL'
            response['Access-Control-Allow-Origin'] = '*'
            response['Content-Security-Policy'] = "frame-ancestors *"
            return response
    return Response({"error": "PDF no encontrado"}, status=status.HTTP_404_NOT_FOUND)

import mercadopago
from decouple import config
from datetime import datetime, timedelta

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def mp_checkout(request):
    plan = request.data.get('plan')
    ciclo = request.data.get('ciclo', 'monthly')
    
    planes = {
        'starter': {'nombre': 'LeadBook Starter', 'precio_mensual': 70000, 'precio_anual': 52500},
        'pro': {'nombre': 'LeadBook Pro', 'precio_mensual': 161000, 'precio_anual': 120750},
        'scale': {'nombre': 'LeadBook Scale', 'precio_mensual': 270000, 'precio_anual': 202500},
        'business': {'nombre': 'LeadBook Business', 'precio_mensual': 542000, 'precio_anual': 406500},
    }
    
    if plan not in planes:
        return Response({"error": "Plan inválido"}, status=400)
    
    plan_data = planes[plan]
    precio = plan_data['precio_anual'] if ciclo == 'annual' else plan_data['precio_mensual']
    nombre = f"{plan_data['nombre']} ({'Anual' if ciclo == 'annual' else 'Mensual'})"
    
    sdk = mercadopago.SDK(config('MP_ACCESS_TOKEN'))
    frontend_url = config('FRONTEND_URL', default='https://front-saas-production-1e0c.up.railway.app')
    
    preference_data = {
        "items": [{
            "id": f"{plan}_{ciclo}",
            "title": nombre,
            "quantity": 1,
            "currency_id": "ARS",
            "unit_price": float(precio)
        }],
        "payer": {"email": request.user.email},
        "back_urls": {
            "success": f"{frontend_url}/pago-exitoso?plan={plan}",
            "failure": f"{frontend_url}/pago-fallido",
            "pending": f"{frontend_url}/pago-pendiente"
        },
        "auto_return": "approved",
        "external_reference": f"{request.user.id}|{plan}",
    }
    
    preference_response = sdk.preference().create(preference_data)
    
    if preference_response["status"] == 201:
        return Response({
            "init_point": preference_response["response"]["init_point"],
            "preference_id": preference_response["response"]["id"]
        })
    else:
        print(f"MP Error: {preference_response}")
        return Response({"error": "Error al crear preferencia de pago"}, status=500)



@api_view(['POST'])
@permission_classes([IsAuthenticated])
def mp_checkout_api_extra(request):
    """Genera link de pago para comprar una API adicional de Gemini"""
    servicio = request.data.get('servicio', 'gemini')
    
    PRECIOS_EXTRA = {
        'gemini':       {'nombre': 'Contenido IA — Adicional (+1500 créditos)',     'precio': 1},
        'elevenlabs':   {'nombre': 'Voces Neurales — Adicional (+10.000 caracteres)', 'precio': 1},
        'uploadpost':   {'nombre': 'Gestor de Redes — Adicional (+10 publicaciones)', 'precio': 1},
        'pack_completo':{'nombre': 'Pack Completo — Todos los recursos',              'precio': 1},
    }
    
    if servicio not in PRECIOS_EXTRA:
        return Response({"error": "Servicio inválido"}, status=400)
    
    item = PRECIOS_EXTRA[servicio]
    sdk = mercadopago.SDK(config('MP_ACCESS_TOKEN'))
    frontend_url = config('FRONTEND_URL', default='https://front-saas-production-1e0c.up.railway.app')
    
    preference_data = {
        "items": [{
            "id": f"extra_{servicio}",
            "title": item['nombre'],
            "description": f"Uso adicional permanente mensual de {item['nombre']}. Se suma a tu límite actual.",
            "quantity": 1,
            "currency_id": "ARS",
            "unit_price": float(item['precio'])
        }],
        "payer": {"email": request.user.email},
        "back_urls": {
            "success": f"{frontend_url}/dashboard?extra=exitoso&servicio={servicio}",
            "failure": f"{frontend_url}/precios?extra=fallido",
            "pending": f"{frontend_url}/dashboard?extra=pendiente"
        },
        "auto_return": "approved",
        "external_reference": f"{request.user.id}|extra_{servicio}",
    }
    
    preference_response = sdk.preference().create(preference_data)
    
    if preference_response["status"] == 201:
        return Response({
            "init_point": preference_response["response"]["init_point"],
            "preference_id": preference_response["response"]["id"]
        })
    else:
        return Response({"error": "Error al crear preferencia de pago"}, status=500)



@api_view(['POST'])
@permission_classes([AllowAny])
def mp_webhook(request):
    topic = request.data.get('type')
    data_id = request.data.get('data', {}).get('id')
    
    if not data_id:
        return Response({"status": "ok"})
    
    try:
        import requests as req
        headers = {"Authorization": f"Bearer {config('MP_ACCESS_TOKEN')}"}
        
        if topic == 'payment':
            response = req.get(
                f"https://api.mercadopago.com/v1/payments/{data_id}",
                headers=headers
            )
        elif topic == 'subscription_preapproval':
            response = req.get(
                f"https://api.mercadopago.com/preapproval/{data_id}",
                headers=headers
            )
        else:
            return Response({"status": "ok"})
        
        data = response.json()
        status = data.get("status")
        external_ref = data.get("external_reference", "")
        
        if status in ["approved", "authorized"] and "|" in external_ref:
            user_id, tipo = external_ref.split("|", 1)
            from .models import Agent
            try:
                agent = Agent.objects.get(id=int(user_id))
                if tipo.startswith('extra_'):
                    # Compra de API adicional
                    if tipo == 'extra_pack_completo':
                        for svc in ['gemini', 'elevenlabs', 'uploadpost']:
                            keys_ya_usadas = BundleAPIExtra.objects.filter(
                                usuario=agent, servicio=svc, activa=True
                            ).values_list('api_key_id', flat=True)
                            key_disponible = APIKey.objects.filter(
                                servicio=svc, status__in=['available', 'active']
                            ).exclude(id__in=keys_ya_usadas).first()
                            if key_disponible:
                                BundleAPIExtra.objects.create(
                                    usuario=agent, api_key=key_disponible,
                                    servicio=svc, activa=True, pago_id=str(data_id)
                                )
                                from .models import UserAPIQuota
                                quota, _ = UserAPIQuota.objects.get_or_create(user=agent, service=svc)
                                quota.is_blocked = False
                                # Incrementos específicos por servicio
                                inc = 1500 if svc == 'gemini' else 10000 if svc == 'elevenlabs' else 10
                                quota.monthly_limit = (quota.monthly_limit or (1500 if svc=='gemini' else 10000 if svc=='elevenlabs' else 10)) + inc
                                quota.daily_limit = (quota.daily_limit or (1500 if svc=='gemini' else 10000 if svc=='elevenlabs' else 10)) + inc
                                quota.save()
                        print(f"[MP] Pack completo asignado: user {user_id}")
                    else:
                        servicio = tipo.replace('extra_', '')
                        from .models import APIKey, BundleAPIExtra
                        # Buscar una APIKey disponible del servicio que no esté asignada como extra
                        keys_ya_usadas = BundleAPIExtra.objects.filter(
                            usuario=agent, servicio=servicio, activa=True
                        ).values_list('api_key_id', flat=True)
                        key_disponible = APIKey.objects.filter(
                            servicio=servicio,
                            status__in=['available', 'active']
                        ).exclude(id__in=keys_ya_usadas).first()
                        
                        if key_disponible:
                            BundleAPIExtra.objects.create(
                                usuario=agent, api_key=key_disponible,
                                servicio=servicio, activa=True, pago_id=str(data_id)
                            )
                            # Actualizar el límite en UserAPIQuota
                            from .models import UserAPIQuota
                            quota, _ = UserAPIQuota.objects.get_or_create(user=agent, service=servicio)
                            quota.is_blocked = False
                            # Aumentar límites (mensual y diario)
                            inc = 1500 if servicio == 'gemini' else 10000 if servicio == 'elevenlabs' else 10
                            quota.monthly_limit = (quota.monthly_limit or inc) + inc
                            quota.daily_limit = (quota.daily_limit or inc) + inc
                            quota.save()
                            print(f"[MP] API extra asignada: user {user_id} → {servicio} extra")
                        else:
                            print(f"[MP] No hay APIKey disponible para {servicio}")
                else:
                    # Compra de plan normal
                    agent.plan_nombre = tipo
                    agent.plan_activo = True
                    agent.save()
                    print(f"[MP] Plan actualizado: user {user_id} → {tipo}")



            except Agent.DoesNotExist:
                print(f"[MP] Usuario no encontrado: {user_id}")
    except Exception as e:
        print(f"[MP] Error webhook: {e}")
    
    return Response({"status": "ok"})

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def plan_status(request):
    user = request.user
    return Response({
        "plan_nombre": user.plan_nombre,
        "plan_activo": user.plan_activo,
        "plan_seleccionado": user.plan_seleccionado,
    })

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def seleccionar_plan_free(request):
    user = request.user
    user.plan_nombre = 'free'
    user.plan_activo = True
    user.plan_seleccionado = True
    user.save()
    return Response({"ok": True, "plan": "free"})

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_plan_info_mp(request):
    from .plan_utils import LIMITES
    from .models import UsageLog
    agent = request.user
    plan = agent.plan_nombre or 'free'
    limites = LIMITES.get(plan, LIMITES['free'])
    now = timezone.now()
    ai_used = UsageLog.objects.filter(
        agent=agent, tipo='ai',
        fecha__year=now.year, fecha__month=now.month
    ).count()
    images_used = UsageLog.objects.filter(
        agent=agent, tipo='image',
        fecha__year=now.year, fecha__month=now.month
    ).count()
    videos_used = UsageLog.objects.filter(
        agent=agent, tipo='video',
        fecha__year=now.year, fecha__month=now.month
    ).count()
    listados_mes = Listado.objects.filter(
        agente=agent,
        creado_en__year=now.year, creado_en__month=now.month
    ).count()
    return Response({
        "plan_nombre": plan,
        "mp_public_key": settings.MP_PUBLIC_KEY,
        "uso_actual": {
            "properties_used": listados_mes,
            "ai_used": ai_used,
            "images_used": images_used,
            "videos_used": videos_used
        },
        "limites": {
            "properties_per_month": limites['properties'],
            "ai_generations": limites['ai'],
            "image_generations": limites['images'],
            "video_generations": limites['videos']
        }
    })


import secrets
import hashlib
from django.core.mail import send_mail
from datetime import timedelta


@api_view(['POST'])
@permission_classes([AllowAny])
def send_otp(request):
    email = request.data.get('email', '').strip().lower()
    if not email:
        return Response({"error": "Email requerido"}, status=400)

    recent = OTPCode.objects.filter(
        email=email,
        created_at__gte=timezone.now() - timedelta(minutes=15)
    ).count()
    if recent >= 3:
        return Response({"error": "Demasiados intentos. Esperá 15 minutos."}, status=429)

    code = str(secrets.randbelow(900000) + 100000)
    code_hash = hashlib.sha256(code.encode()).hexdigest()
    expires_at = timezone.now() + timedelta(minutes=10)

    OTPCode.objects.create(
        email=email,
        code_hash=code_hash,
        expires_at=expires_at
    )

    # Envío del OTP robusto: intenta Celery asíncrono; si falla o no hay broker,
    # cae a envío síncrono en el request. Así funciona en Railway sin worker.
    import sys
    from django.conf import settings

    # Log de diagnóstico MUY visible en Railway
    print(f"[EMAIL] Intentando enviar a {email}", flush=True)
    print(
        f"[EMAIL] DIAG backend={settings.EMAIL_BACKEND} "
        f"host={settings.EMAIL_HOST}:{settings.EMAIL_PORT} "
        f"user_set={bool(settings.EMAIL_HOST_USER)} "
        f"pass_set={bool(settings.EMAIL_HOST_PASSWORD)} "
        f"eager={getattr(settings, 'CELERY_TASK_ALWAYS_EAGER', True)}",
        flush=True,
    )
    sys.stdout.flush()

    sent_mode = None
    try:
        from .tasks import send_otp_email_async

        if getattr(settings, 'CELERY_TASK_ALWAYS_EAGER', True):
            # Eager: ejecutar la task sincronamente sin broker
            send_otp_email_async(email, code)
            sent_mode = 'sync-eager'
        else:
            # Intentar enviar al broker Celery (Redis)
            send_otp_email_async.delay(email, code)
            sent_mode = 'celery-queued'
        print(f"[EMAIL] Enviado correctamente a {email} (mode={sent_mode})", flush=True)
    except Exception as e_celery:
        # Broker caído, sin Redis, o cualquier otro problema: fallback sync
        print(f"[EMAIL] ERROR al enviar (celery path): {type(e_celery).__name__}: {str(e_celery)}", flush=True)
        print(f"[EMAIL] Intentando fallback sync a {email}", flush=True)
        try:
            from .tasks import send_otp_email_async as _send_sync
            _send_sync(email, code)
            sent_mode = 'sync-fallback'
            print(f"[EMAIL] Enviado correctamente a {email} (mode={sent_mode})", flush=True)
        except Exception as e_sync:
            print(f"[EMAIL] ERROR al enviar: {str(e_sync)}", flush=True)
            import traceback
            traceback.print_exc()
            sent_mode = f'error:{type(e_sync).__name__}'

    sys.stdout.flush()
    return Response({"mensaje": "Código enviado", "email": email, "_mode": sent_mode})


@api_view(['POST'])
@permission_classes([AllowAny])
def verify_otp(request):
    email = request.data.get('email', '').strip().lower()
    code = request.data.get('code', '').strip()

    if not email or not code:
        return Response({"error": "Email y código requeridos"}, status=400)

    otp = OTPCode.objects.filter(
        email=email,
        verified=False
    ).order_by('-created_at').first()

    if not otp:
        return Response({"error": "Código inválido o ya utilizado"}, status=400)

    if otp.is_expired():
        return Response({"error": "Código expirado. Pedí uno nuevo."}, status=400)

    if otp.attempts >= 5:
        return Response({"error": "Demasiados intentos. Pedí un nuevo código."}, status=429)

    # Verificar hash ANTES de incrementar attempts para no penalizar el intento correcto
    code_hash = OTPCode.hash_code(code)
    if otp.code_hash != code_hash:
        otp.attempts += 1
        otp.save()
        intentos_restantes = 5 - otp.attempts
        return Response({"error": f"Código incorrecto. {intentos_restantes} intentos restantes."}, status=400)

    # Código correcto
    otp.verified = True
    otp.save()

    return Response({"verificado": True, "email": email})


@api_view(['POST'])
@permission_classes([AllowAny])
def recuperar_password(request):
    from .models import Agent
    email = request.data.get('email', '').strip().lower()
    if not email:
        return Response({"error": "Email requerido"}, status=400)
    
    user = Agent.objects.filter(email=email).first()
    if not user:
        return Response({"error": "No encontramos una cuenta con ese email"}, status=404)
    
    import secrets
    import hashlib
    from datetime import timedelta
    from django.utils import timezone
    
    code = str(secrets.randbelow(900000) + 100000)
    code_hash = hashlib.sha256(code.encode()).hexdigest()
    expires_at = timezone.now() + timedelta(minutes=10)
    
    OTPCode.objects.create(
        email=email,
        code_hash=code_hash,
        expires_at=expires_at,
        tipo="recuperacion"
    )

    # Envío robusto con fallback síncrono (idéntico a send_otp)
    try:
        from django.conf import settings
        from .tasks import send_otp_email_async
        if getattr(settings, 'CELERY_TASK_ALWAYS_EAGER', True):
            send_otp_email_async(email, code)
        else:
            send_otp_email_async.delay(email, code)
    except Exception as e_celery:
        print(f"[OTP-RECOV] Celery falló ({e_celery}). Fallback sync.")
        try:
            from .tasks import send_otp_email_async as _send_sync
            _send_sync(email, code)
        except Exception as e_sync:
            print(f"[OTP-RECOV] ERROR envío síncrono: {e_sync}")

    return Response({"mensaje": "Código enviado", "email": email}, status=200)


@api_view(['POST'])
@permission_classes([AllowAny])
def confirmar_recuperacion(request):
    from .models import Agent
    email = request.data.get('email', '').strip().lower()
    code = request.data.get('codigo', '').strip()
    nueva_password = request.data.get('nueva_password', '')
    
    if not email or not code or not nueva_password:
        return Response({"error": "Faltan datos requeridos"}, status=400)
    
    otp = OTPCode.objects.filter(
        email=email,
        tipo="recuperacion",
        verified=False
    ).order_by('-created_at').first()
    
    if not otp:
        return Response({"error": "Código inválido"}, status=400)
    if otp.is_expired():
        return Response({"error": "Código expirado"}, status=400)
    if not otp.is_valid(code):
        return Response({"error": "Código incorrecto"}, status=400)
    
    user = Agent.objects.filter(email=email).first()
    if not user:
        return Response({"error": "Usuario no encontrado"}, status=404)
    
    user.set_password(nueva_password)
    user.save()
    
    otp.verified = True
    otp.save()
    
    return Response({"mensaje": "Contraseña actualizada correctamente"}, status=200)


@api_view(['GET'])
@permission_classes([AllowAny])
def obtener_terminos(request):
    """Devuelve los Términos y Condiciones vigentes"""
    try:
        terminos = TerminosCondiciones.objects.filter(activo=True).latest('fecha_actualizacion')
        serializer = TerminosCondicionesSerializer(terminos)
        return Response(serializer.data)
    except TerminosCondiciones.DoesNotExist:
        return Response({"error": "Términos no disponibles"}, status=404)

@api_view(['GET'])
@permission_classes([AllowAny])
def obtener_politica_privacidad(request):
    """Devuelve la Política de Privacidad vigente"""
    try:
        politica = PoliticaPrivacidad.objects.filter(activo=True).latest('fecha_actualizacion')
        serializer = PoliticaPrivacidadSerializer(politica)
        return Response(serializer.data)
    except PoliticaPrivacidad.DoesNotExist:
        return Response({"error": "Política de privacidad no disponible"}, status=404)

@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def amenidades_presets(request):
    from .models import AmenidadPreset
    agente = request.user
    if request.method == 'GET':
        presets = AmenidadPreset.objects.filter(agente=agente)
        return Response({'presets': [p.nombre for p in presets]})
    
    if request.method == 'POST':
        nombre = request.data.get('nombre', '').strip()
        if not nombre:
            return Response({'error': 'Nombre requerido'}, status=400)
        preset, created = AmenidadPreset.objects.get_or_create(
            agente=agente, nombre=nombre
        )
        return Response({
            'nombre': preset.nombre, 
            'created': created
        }, status=201 if created else 200)

from django.utils import timezone
from datetime import timedelta

ADMIN_KEY = config('ADMIN_KEY', default='')

def check_admin(request):
    return request.headers.get('X-Admin-Key') == ADMIN_KEY

@api_view(['GET'])
@permission_classes([AllowAny])
def admin_stats(request):
    """
    Dashboard de administración: Métricas globales y estado detallado de las APIs asignadas.
    """
    if not check_admin(request):
        return Response({"error": "Forbidden"}, status=403)
    
    from .models import Agent, APIKey, UserAPIQuota, APIBundleAssignment
    from django.utils import timezone
    from datetime import timedelta

    ahora = timezone.now()
    hoy = ahora - timedelta(hours=24)
    semana = ahora - timedelta(days=7)
    
    from .models import Agent, Listado
    
    total = Agent.objects.count()
    activos_hoy = Agent.objects.filter(
        last_login__gte=hoy).count()
    activos_semana = Agent.objects.filter(
        last_login__gte=semana).count()
    nuevos_hoy = Agent.objects.filter(
        fecha_registro__gte=hoy).count()
    nuevos_semana = Agent.objects.filter(
        fecha_registro__gte=semana).count()
    
    distribucion = {}
    for plan in ['free','starter','pro','scale','business']:
        distribucion[plan] = Agent.objects.filter(
            plan_nombre=plan).count()
    
    try:
        total_listados = Listado.objects.count()
    except:
        total_listados = 0
    
    return Response({
        "total_usuarios": total,
        "activos_hoy": activos_hoy,
        "activos_semana": activos_semana,
        "nuevos_hoy": nuevos_hoy,
        "nuevos_semana": nuevos_semana,
        "distribucion_planes": distribucion,
        "total_listados": total_listados
    })

@api_view(['GET'])
@permission_classes([AllowAny])
def admin_usuarios(request):
    if not check_admin(request):
        return Response({"error": "Forbidden"}, status=403)
    try:
        from .models import Agent, Listado
        incluir_eliminados = request.query_params.get('incluir_eliminados') in ('1', 'true', 'True')
        agentes_qs = Agent.objects.all().order_by('-fecha_registro')
        if not incluir_eliminados:
            try:
                agentes_qs = agentes_qs.filter(eliminado_en__isnull=True)
            except Exception as e:
                import sys
                print(f"[admin_usuarios] WARN filter eliminado_en fallo: {e}", file=sys.stderr, flush=True)
        
        resultado = []
        for a in agentes_qs:
            try:
                listados = Listado.objects.filter(agente=a).count()
            except:
                listados = 0
            
            resultado.append({
                "id": a.id,
                "email": a.email,
                "nombre": getattr(a, 'nombre', ''),
                "agencia": getattr(a, 'agencia', '') or getattr(a, 'nombre_inmobiliaria', ''),
                "plan_nombre": getattr(a, 'plan_nombre', 'free'),
                "plan_activo": getattr(a, 'plan_activo', True),
                "fecha_registro": a.fecha_registro.strftime('%Y-%m-%d %H:%M') if a.fecha_registro else '',
                "last_login": a.last_login.strftime('%Y-%m-%d %H:%M') if a.last_login else 'Nunca',
                "listados_count": listados,
                "pais": getattr(a, 'pais', ''),
                "nicho": getattr(a, 'nicho', ''),
            })
        return Response({"usuarios": resultado})
    except Exception as e:
        import traceback, sys
        traceback.print_exc(file=sys.stderr)
        sys.stderr.flush()
        return Response({"error": "internal", "detail": str(e)[:300]}, status=500)

@api_view(['DELETE'])
@permission_classes([AllowAny])
def admin_eliminar_usuario(request, user_id):
    if not check_admin(request):
        return Response({"error": "Forbidden"}, status=403)
    
    from .models import Agent
    try:
        agent = Agent.objects.get(id=user_id)
        agent.delete()
        return Response({"mensaje": "Usuario eliminado"})
    except Agent.DoesNotExist:
        return Response({"error": "No encontrado"}, status=404)

@api_view(['POST'])
@permission_classes([AllowAny])
def admin_cambiar_plan(request, user_id):
    if not check_admin(request):
        return Response({"error": "Forbidden"}, status=403)
    
    nuevo_plan = request.data.get('plan')
    planes_validos = ['free','starter','pro','scale','business']
    
    if nuevo_plan not in planes_validos:
        return Response({"error": "Plan inválido"}, status=400)
    
    from .models import Agent
    try:
        agent = Agent.objects.get(id=user_id)
        agent.plan_nombre = nuevo_plan
        agent.save()
        return Response({
            "mensaje": f"Plan actualizado a {nuevo_plan}",
            "plan": nuevo_plan
        })
    except Agent.DoesNotExist:
        return Response({"error": "No encontrado"}, status=404)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def dashboard(request):
    agent = request.user
    now = timezone.now()
    start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    from .models import Listado, UsageLog
    from .plan_utils import LIMITES

    listados = Listado.objects.filter(agente=agent)
    listados_este_mes = listados.filter(creado_en__gte=start_of_month).count()
    total_generados = listados.count()
    videos_creados = listados.aggregate(total=Sum('videos_creados'))['total'] or 0

    listados_recientes = list(listados.order_by('-creado_en')[:5].values(
        'id', 'titulo', 'tipo_propiedad', 'ciudad', 'precio', 'creado_en'
    ))

    plan = agent.plan_nombre or 'free'
    limites = LIMITES.get(plan, LIMITES['free'])

    # Uso actual del mes (via UsageLog)
    ai_used = UsageLog.objects.filter(
        agent=agent, tipo='ai',
        fecha__year=now.year, fecha__month=now.month
    ).count()
    images_used = UsageLog.objects.filter(
        agent=agent, tipo='image',
        fecha__year=now.year, fecha__month=now.month
    ).count()
    videos_used = UsageLog.objects.filter(
        agent=agent, tipo='video',
        fecha__year=now.year, fecha__month=now.month
    ).count()

    return Response({
        'nombre_inmobiliaria': getattr(agent, 'nombre_inmobiliaria', None),
        'logo_url': getattr(agent, 'logo_url', None),
        'listados_este_mes': listados_este_mes,
        'total_generados': total_generados,
        'videos_creados': videos_creados,
        'conexiones_activas': 0,
        'listados_recientes': listados_recientes,
        'plan': plan,
        'plan_limites': {
            'properties_per_month': limites['properties'],
            'ai_generations': limites['ai'],
            'image_generations': limites['images'],
            'video_generations': limites['videos'],
            'branding': plan not in ('free',),
        },
        'uso_actual': {
            'properties_used': listados_este_mes,
            'ai_used': ai_used,
            'images_used': images_used,
            'videos_used': videos_used,
        }
    })

@api_view(['GET'])
@permission_classes([AllowAny])
def admin_listados(request):
    """Todos los listados del sistema"""
    if not check_admin(request):
        return Response({"error": "Forbidden"}, status=403)
    from .models import Listado
    listados = Listado.objects.select_related('agente').order_by('-creado_en')[:100]
    data = [{
        "id": l.id,
        "titulo": l.titulo,
        "tipo": l.tipo_propiedad,
        "ciudad": l.ciudad,
        "precio": str(l.precio) if l.precio else None,
        "agente_email": l.agente.email,
        "agente_nombre": l.agente.nombre,
        "video_status": l.video_status,
        "creado_en": l.creado_en.strftime('%Y-%m-%d %H:%M') if l.creado_en else ''
    } for l in listados]
    return Response({"listados": data, "total": len(data)})

@api_view(['GET'])
@permission_classes([AllowAny])
def admin_assets(request):
    """Stats de assets generados"""
    if not check_admin(request):
        return Response({"error": "Forbidden"}, status=403)
    from .models import GeneratedAsset
    total = GeneratedAsset.objects.count()
    por_tipo = {}
    for tipo in ['PDF', 'VIDEO', 'EMAIL', 'SOCIAL']:
        por_tipo[tipo] = GeneratedAsset.objects.filter(asset_type=tipo).count()
    por_status = {}
    for status in ['PENDING', 'PROCESSING', 'COMPLETED', 'FAILED']:
        por_status[status] = GeneratedAsset.objects.filter(status=status).count()
    return Response({
        "total": total,
        "por_tipo": por_tipo,
        "por_status": por_status
    })

@api_view(['GET'])
@permission_classes([AllowAny])
def admin_pagos(request):
    """Historial de pagos/planes"""
    if not check_admin(request):
        return Response({"error": "Forbidden"}, status=403)
    from .models import Agent
    agentes_pagos = Agent.objects.exclude(
        plan_nombre='free'
    ).order_by('-fecha_registro')
    data = [{
        "email": a.email,
        "nombre": a.nombre,
        "plan": a.plan_nombre,
        "plan_activo": a.plan_activo,
        "mp_customer_id": a.mp_customer_id or '',
        "mp_subscription_id": a.mp_subscription_id or '',
        "fecha_registro": a.fecha_registro.strftime('%Y-%m-%d') if a.fecha_registro else ''
    } for a in agentes_pagos]
    return Response({"pagos": data, "total_pagos": len(data)})

@api_view(['GET'])
@permission_classes([AllowAny])
def admin_usuario_detalle(request, user_id):
    """Detalle completo de un usuario"""
    if not check_admin(request):
        return Response({"error": "Forbidden"}, status=403)
    from .models import Agent, Listado
    try:
        a = Agent.objects.get(id=user_id)
    except Agent.DoesNotExist:
        return Response({"error": "Usuario no encontrado"}, status=404)
    listados = Listado.objects.filter(agente=a).order_by('-creado_en')
    return Response({
        "id": a.id,
        "email": a.email,
        "nombre": a.nombre,
        "agencia": a.agencia or '',
        "telefono": a.telefono or '',
        "pais": a.pais or '',
        "nicho": a.nicho or '',
        "plan": a.plan_nombre,
        "plan_activo": a.plan_activo,
        "is_active": a.is_active,
        "fecha_registro": a.fecha_registro.strftime('%Y-%m-%d %H:%M') if a.fecha_registro else '',
        "last_login": a.last_login.strftime('%Y-%m-%d %H:%M') if a.last_login else 'Nunca',
        "total_listados": listados.count(),
        "listados_recientes": [{
            "titulo": l.titulo,
            "tipo": l.tipo_propiedad,
            "ciudad": l.ciudad,
            "creado_en": l.creado_en.strftime('%Y-%m-%d') if l.creado_en else ''
        } for l in listados[:10]]
    })


@api_view(['GET', 'POST'])
@permission_classes([AllowAny])
def admin_suspender_usuario(request, user_id):
    """Suspender o reactivar un usuario"""
    if not check_admin(request):
        return Response({"error": "Forbidden"}, status=403)
    if request.method != 'POST':
        return Response({"error": "Method not allowed"}, status=405)
    from .models import Agent
    try:
        a = Agent.objects.get(id=user_id)
    except Agent.DoesNotExist:
        return Response({"error": "Usuario no encontrado"}, status=404)
    a.is_active = not a.is_active
    a.save()
    estado = "suspendido" if not a.is_active else "reactivado"
    return Response({"ok": True, "estado": estado, "is_active": a.is_active})

import requests as http_requests

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def conexiones_init(request):
    """
    Crea perfil en UploadPost para el usuario y devuelve 
    la URL segura para conectar sus redes sociales.
    """
    import traceback, sys
    try:
        from django.conf import settings
        from api.pool_manager import get_api_key
        import os
        
        user = request.user
        username = f"leadbook_{user.id}"
        print(f"[conexiones_init] user={user.email} username={username}", flush=True)
        
        # 1. Key del bundle/pool del usuario
        api_key = get_api_key(user, 'uploadpost')
        
        # 2. Fallback: key global del .env de producción
        if not api_key:
            api_key = (
                getattr(settings, 'UPLOADPOST_API_KEY', '') or
                os.environ.get('UPLOADPOST_API_KEY', '') or
                os.environ.get('UPLOAD_POST_API_KEY', '')
            ) or None
            if api_key:
                print(f"[conexiones_init] Usando UPLOADPOST_API_KEY global para {user.email}", flush=True)
        
        if not api_key:
            print(f"[conexiones_init] Sin key uploadpost para {user.email}. Plan={getattr(user, 'plan_nombre', 'free')}", flush=True)
            return Response({
                "success": False,
                "error": "Tu cuenta no tiene una API de publicación asignada. Contactá a soporte."
            }, status=400)
        
        headers = {
            "Authorization": f"Apikey {api_key}",
            "Content-Type": "application/json"
        }
        
        # PASO 1: Crear perfil (si no existe)
        create_resp = http_requests.post(
            "https://api.upload-post.com/api/uploadposts/users",
            headers=headers,
            json={"username": username},
            timeout=10
        )
        print(f"[conexiones_init] create_profile status={create_resp.status_code}", flush=True)
        # 200 o 409 (ya existe) son aceptables
        if create_resp.status_code not in [200, 201, 409]:
            err_text = create_resp.text[:200]
            if "PROFILE_LIMIT_REACHED" in err_text or "limit of 2 profiles" in err_text:
                return Response({
                    "success": False,
                    "error": "Alcanzaste el límite de cuentas vinculadas de tu plan actual. Para conectar más redes sociales, por favor mejorá a un Plan Pro."
                }, status=400)
                
            return Response({
                "success": False,
                "error": f"Error al vincular: {err_text}"
            }, status=500)
        
        platform = request.data.get('platform')
        
        jwt_payload = {
            "username": username,
            "redirect_url": f"{settings.FRONTEND_URL}/conexiones",
            "logo_image": "https://res.cloudinary.com/dpqgbgilw/image/upload/leadbook_logo",
            "connect_title": "Conectá tus redes sociales",
            "connect_description": "Conectá tus cuentas para publicar automáticamente con LeadBook",
            "show_calendar": True
        }
        # Si viene una plataforma específica, pre-seleccionarla en el wizard de UploadPost
        if platform:
            jwt_payload["platform"] = platform
            
        jwt_resp = http_requests.post(
            "https://api.upload-post.com/api/uploadposts/users/generate-jwt",
            headers=headers,
            json=jwt_payload,
            timeout=10
        )
        print(f"[conexiones_init] generate_jwt status={jwt_resp.status_code}", flush=True)
        if jwt_resp.status_code != 200:
            return Response({
                "success": False,
                "error": f"Error generando URL: {jwt_resp.text[:200]}"
            }, status=500)
        
        data = jwt_resp.json()
        return Response({
            "success": True,
            "access_url": data.get("access_url"),
            "username": username
        })
    except Exception as e:
        print(f"[conexiones_init] EXCEPTION: {e}", file=sys.stderr, flush=True)
        traceback.print_exc(file=sys.stderr)
        return Response({
            "success": False,
            "error": f"Error interno del servidor: {str(e)[:200]}"
        }, status=500)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def conexiones_eliminar(request):
    """
    Elimina el perfil del usuario en UploadPost (desvincula todas las redes y libera el límite de la API).
    """
    try:
        from api.pool_manager import get_api_key
        user = request.user
        username = f"leadbook_{user.id}"
        api_key = get_api_key(user, 'uploadpost')
        
        if not api_key:
            return Response({"success": False, "error": "No se encontró API Key vinculada para este usuario"}, status=400)
            
        headers = {
            "Authorization": f"Apikey {api_key}",
            "Content-Type": "application/json"
        }
        
        resp = http_requests.delete(
            "https://api.upload-post.com/api/uploadposts/users",
            headers=headers,
            json={"username": username},
            timeout=10
        )
        
        if resp.status_code in [200, 204]:
            return Response({"success": True, "message": "Perfil eliminado. Podés volver a vincular tus cuentas."})
        else:
            return Response({"success": False, "error": f"Error al eliminar: {resp.text[:200]}"}, status=400)
            
    except Exception as e:
        return Response({"success": False, "error": f"Error interno: {str(e)[:100]}"}, status=500)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def conexiones_estado(request):
    """
    Devuelve las redes sociales conectadas del usuario consultando UploadPost.
    Siempre devuelve JSON — nunca HTML.
    """
    import traceback, sys, os
    try:
        from api.pool_manager import get_api_key
        from django.conf import settings

        user = request.user
        username = f"leadbook_{user.id}"
        print(f"[conexiones_estado] user={user.email} username={username}", flush=True)

        # 1. Key del pool del usuario
        api_key = get_api_key(user, 'uploadpost')

        # 2. Fallback a key global de .env
        if not api_key:
            api_key = (
                getattr(settings, 'UPLOADPOST_API_KEY', '') or
                os.environ.get('UPLOADPOST_API_KEY', '') or
                os.environ.get('UPLOAD_POST_API_KEY', '')
            ) or None
            if api_key:
                print(f"[conexiones_estado] Usando key global para {user.email}", flush=True)

        if not api_key:
            print(f"[conexiones_estado] Sin key uploadpost para {user.email}", flush=True)
            return Response({"success": True, "redes": [], "conectado": False})

        headers = {
            "Authorization": f"Apikey {api_key}",
            "Content-Type": "application/json"
        }

        # ESTRATEGIA 1: Endpoint específico del usuario (más preciso)
        perfil = None
        resp_individual = http_requests.get(
            f"https://api.upload-post.com/api/uploadposts/users/{username}",
            headers=headers,
            timeout=10
        )
        print(f"[conexiones_estado] GET /users/{username} → status={resp_individual.status_code}", flush=True)

        if resp_individual.status_code == 200:
            try:
                perfil = resp_individual.json()
                print(f"[conexiones_estado] perfil individual={perfil}", flush=True)
            except Exception:
                perfil = None

        # ESTRATEGIA 2: Listar todos y buscar (fallback)
        if not perfil:
            resp_list = http_requests.get(
                "https://api.upload-post.com/api/uploadposts/users",
                headers=headers,
                timeout=10
            )
            print(f"[conexiones_estado] GET /users list → status={resp_list.status_code}", flush=True)
            if resp_list.status_code == 200:
                try:
                    raw = resp_list.json()
                    print(f"[conexiones_estado] raw list response (first 500 chars)={str(raw)[:500]}", flush=True)
                    # Normalizar a lista
                    if isinstance(raw, list):
                        usuarios = raw
                    elif isinstance(raw, dict):
                        usuarios = raw.get('users') or raw.get('data') or raw.get('results') or []
                    else:
                        usuarios = []
                    perfil = next(
                        (u for u in usuarios if u.get("username") == username),
                        None
                    )
                except Exception as parse_err:
                    print(f"[conexiones_estado] Error parseando lista: {parse_err}", flush=True)

        if not perfil:
            print(f"[conexiones_estado] Perfil '{username}' no encontrado en UploadPost", flush=True)
            return Response({"success": True, "redes": [], "conectado": False, "username": username})

        # Obtener el objeto de redes.
        # UploadPost devuelve {"success": true, "profile": {"social_accounts": {"instagram": {...}, "tiktok": ""}}}
        if "profile" in perfil:
            social_accounts = perfil["profile"].get("social_accounts", {})
        else:
            social_accounts = perfil.get("social_accounts", {})

        print(f"[conexiones_estado] social_accounts={social_accounts}", flush=True)

        redes_normalizadas = []
        
        # Iterar sobre las claves del diccionario (ej: "instagram", "tiktok")
        if isinstance(social_accounts, dict):
            for platform, data in social_accounts.items():
                # Si el valor está vacío (ej: ""), significa que no está conectado
                if not data:
                    continue
                    
                # Si es un dict, extraer la info
                if isinstance(data, dict):
                    # Ignorar si requiere reconexión
                    if data.get("reauth_required") is True:
                        continue
                        
                    redes_normalizadas.append({
                        "platform": platform,
                        "username": data.get("handle") or data.get("display_name") or data.get("username") or "",
                        "status": "connected"
                    })
                elif isinstance(data, str) and data:
                    # Por si acaso devuelve un string no vacío
                    redes_normalizadas.append({
                        "platform": platform,
                        "username": data,
                        "status": "connected"
                    })

        return Response({
            "success": True,
            "conectado": len(redes_normalizadas) > 0,
            "redes": redes_normalizadas,
            "username": username,
            "total": len(redes_normalizadas)
            # Removemos debug_raw_perfil porque ya vimos la estructura
        })

    except Exception as e:
        print(f"[conexiones_estado] EXCEPTION: {e}", file=sys.stderr, flush=True)
        traceback.print_exc(file=sys.stderr)
        return Response({
            "success": False,
            "redes": [],
            "conectado": False,
            "error": f"Error interno: {str(e)[:200]}"
        }, status=500)



# ============================================================
# DEBUG / DIAGNÓSTICO — endpoints seguros (no exponen secretos)
# Uso: curl https://tuback.up.railway.app/api/v1/debug/email-check/
# ============================================================

@api_view(['GET'])
@permission_classes([AllowAny])
def debug_uploadpost(request, username):
    """
    Endpoint temporal para ver la estructura exacta que devuelve UploadPost
    para un usuario específico.
    """
    import os
    from django.conf import settings
    
    api_key = (
        getattr(settings, 'UPLOADPOST_API_KEY', '') or
        os.environ.get('UPLOADPOST_API_KEY', '') or
        os.environ.get('UPLOAD_POST_API_KEY', '')
    )
    
    if not api_key:
        return Response({"error": "No global UPLOADPOST_API_KEY"}, status=500)
        
    headers = {
        "Authorization": f"Apikey {api_key}",
        "Content-Type": "application/json"
    }
    
    # Probar endpoint individual
    resp1 = http_requests.get(
        f"https://api.upload-post.com/api/uploadposts/users/{username}",
        headers=headers,
        timeout=10
    )
    
    # Probar endpoint lista
    resp2 = http_requests.get(
        "https://api.upload-post.com/api/uploadposts/users",
        headers=headers,
        timeout=10
    )
    
    list_data = None
    if resp2.status_code == 200:
        try:
            raw = resp2.json()
            if isinstance(raw, list): usuarios = raw
            elif isinstance(raw, dict): usuarios = raw.get('users') or raw.get('data') or raw.get('results') or []
            else: usuarios = []
            list_data = next((u for u in usuarios if u.get("username") == username), None)
        except: pass
        
    return Response({
        "target_username": username,
        "strategy_1_individual": {
            "status": resp1.status_code,
            "data": resp1.json() if resp1.status_code == 200 else resp1.text[:200]
        },
        "strategy_2_list": {
            "status": resp2.status_code,
            "found_in_list": list_data
        }
    })

@api_view(['GET'])
@permission_classes([AllowAny])
def debug_email_check(request):
    """
    Devuelve metadata de la config de email sin exponer la password.
    Sirve para verificar si las env vars GMAIL_USER y GMAIL_APP_PASSWORD
    están cargadas en Railway (o cualquier entorno).
    """
    from django.conf import settings
    host_user = getattr(settings, 'EMAIL_HOST_USER', '') or ''
    host_pass = getattr(settings, 'EMAIL_HOST_PASSWORD', '') or ''

    # Enmascarar el user (mostrar solo primeros/últimos chars)
    def mask(s, head=3, tail=3):
        if not s:
            return None
        if len(s) <= head + tail:
            return "*" * len(s)
        return f"{s[:head]}***{s[-tail:]}"

    import os
    provider    = (os.environ.get("EMAIL_PROVIDER") or getattr(settings, "EMAIL_PROVIDER", "") or "gmail").strip().lower()
    resend_key  = os.environ.get("RESEND_API_KEY") or getattr(settings, "RESEND_API_KEY", "") or ""
    resend_from = os.environ.get("RESEND_FROM") or getattr(settings, "RESEND_FROM", "") or ""

    # Verdict operativo unificado
    if provider == "resend":
        if resend_key:
            verdict = "RESEND-OK-listo-para-enviar"
        else:
            verdict = "RESEND-seleccionado-pero-falta-RESEND_API_KEY"
    else:
        if bool(host_user) and bool(host_pass):
            verdict = "SMTP-OK-listo-para-enviar"
        else:
            verdict = "CONSOLE-BACKEND-emails-NO-saldran-cargar-GMAIL_APP_PASSWORD"

    return Response({
        "EMAIL_PROVIDER": provider,
        "EMAIL_BACKEND": getattr(settings, 'EMAIL_BACKEND', None),
        "EMAIL_HOST": getattr(settings, 'EMAIL_HOST', None),
        "EMAIL_PORT": getattr(settings, 'EMAIL_PORT', None),
        "EMAIL_USE_SSL": getattr(settings, 'EMAIL_USE_SSL', None),
        "EMAIL_USE_TLS": getattr(settings, 'EMAIL_USE_TLS', None),
        "DEFAULT_FROM_EMAIL": getattr(settings, 'DEFAULT_FROM_EMAIL', None),
        "GMAIL_USER_set": bool(host_user),
        "GMAIL_USER_masked": mask(host_user),
        "GMAIL_APP_PASSWORD_set": bool(host_pass),
        "GMAIL_APP_PASSWORD_len": len(host_pass),
        "RESEND_API_KEY_set": bool(resend_key),
        "RESEND_API_KEY_len": len(resend_key),
        "RESEND_FROM": resend_from or None,
        "CELERY_TASK_ALWAYS_EAGER": getattr(settings, 'CELERY_TASK_ALWAYS_EAGER', None),
        "DEBUG": getattr(settings, 'DEBUG', None),
        "verdict": verdict,
    })


@api_view(['POST'])
@permission_classes([AllowAny])
def debug_email_send(request):
    """
    Dispara un envío SMTP REAL y SINCRÓNICO de prueba.
    Body JSON: {"email": "destino@mail.com"}  (acepta también "to")
    Devuelve exactamente lo que pasó, incluyendo error SMTP completo si falla.

    IMPORTANTE: En producción deberías proteger este endpoint con
    X-Admin-Key antes de dejarlo abierto. Aquí queda AllowAny para debug rápido.
    """
    import traceback, socket, smtplib, ssl, time
    from django.conf import settings
    from django.core.mail import get_connection, EmailMultiAlternatives

    # Aceptar "email" o "to" (compatibilidad)
    destino = (request.data.get('email') or request.data.get('to') or '').strip().lower()
    if not destino:
        return Response({"error": "falta campo 'email' con el email destino"}, status=400)

    # Provider opcional — si se pasa "resend", probamos Resend sin tocar env vars
    forced_provider = (request.data.get('provider') or '').strip().lower()
    if forced_provider == 'resend':
        import os, traceback
        try:
            from .tasks import _send_via_resend
        except Exception as e_imp:
            return Response({
                "ok": False, "stage": "import-resend",
                "error_type": type(e_imp).__name__, "error": str(e_imp),
            }, status=500)
        print(f"[DEBUG-EMAIL] Forzando envío via RESEND a {destino}", flush=True)
        subject = "LeadBook — prueba de email (Resend, debug)"
        text_body = "Este es un email de prueba enviado por /api/v1/debug/email-send/ (provider=resend)."
        html_body = (
            "<p>Este es un email de prueba enviado por <code>/api/v1/debug/email-send/</code> "
            "(<b>provider=resend</b>).</p><p>Si lo estás leyendo, Resend funciona desde este servidor.</p>"
        )
        try:
            ok, detalle = _send_via_resend(destino, subject, text_body, html_body)
            return Response({
                "ok": ok,
                "stage": "resend",
                "result": detalle,
                "destino": destino,
                "provider": "resend",
                "RESEND_API_KEY_set": bool(os.environ.get("RESEND_API_KEY") or getattr(settings, "RESEND_API_KEY", "")),
                "RESEND_FROM": os.environ.get("RESEND_FROM") or getattr(settings, "RESEND_FROM", "") or None,
            }, status=200 if ok else 500)
        except Exception as e_res:
            return Response({
                "ok": False, "stage": "resend",
                "error_type": type(e_res).__name__, "error": str(e_res),
                "traceback": traceback.format_exc()[-1500:],
            }, status=500)

    host      = getattr(settings, 'EMAIL_HOST', '')
    port      = getattr(settings, 'EMAIL_PORT', 0)
    use_ssl   = getattr(settings, 'EMAIL_USE_SSL', False)
    use_tls   = getattr(settings, 'EMAIL_USE_TLS', False)
    host_user = getattr(settings, 'EMAIL_HOST_USER', '') or ''
    host_pass = getattr(settings, 'EMAIL_HOST_PASSWORD', '') or ''
    from_addr = getattr(settings, 'DEFAULT_FROM_EMAIL', host_user)

    info = {
        "destino": destino,
        "backend": settings.EMAIL_BACKEND,
        "host": host,
        "port": port,
        "use_ssl": use_ssl,
        "use_tls": use_tls,
        "user_set": bool(host_user),
        "user_masked": (host_user[:3] + "***" + host_user[-3:]) if host_user else None,
        "pass_set": bool(host_pass),
        "pass_len": len(host_pass),
        "from": from_addr,
    }

    print(f"[DEBUG-EMAIL] Disparando envío de test a {destino} — host={host}:{port} ssl={use_ssl} tls={use_tls}", flush=True)

    # Guardas tempranas
    if not host_user or not host_pass:
        return Response({
            "ok": False,
            "stage": "env-vars",
            "error": "GMAIL_USER o GMAIL_APP_PASSWORD no están cargadas en el entorno",
            **info,
        }, status=500)

    # 1) Prueba de conectividad TCP pura
    t0 = time.time()
    try:
        sock = socket.create_connection((host, port), timeout=15)
        sock.close()
        tcp_ok = True
        tcp_ms = int((time.time() - t0) * 1000)
    except Exception as e_tcp:
        return Response({
            "ok": False,
            "stage": "tcp-connect",
            "error_type": type(e_tcp).__name__,
            "error": str(e_tcp),
            "hint": "Railway no puede abrir el puerto SMTP. Gmail en la nube suele fallar aquí → migrar a Resend.",
            **info,
        }, status=500)

    # 2) Handshake SMTP + login con smtplib directo para capturar respuesta exacta del server
    smtp_debug = {"tcp_ok": tcp_ok, "tcp_ms": tcp_ms}
    try:
        ctx = ssl.create_default_context()
        if use_ssl:
            smtp = smtplib.SMTP_SSL(host, port, timeout=30, context=ctx)
        else:
            smtp = smtplib.SMTP(host, port, timeout=30)
            if use_tls:
                smtp.starttls(context=ctx)
        ehlo_code, ehlo_msg = smtp.ehlo()
        smtp_debug["ehlo_code"] = ehlo_code
        smtp_debug["ehlo_msg"] = (ehlo_msg or b"").decode(errors="ignore")[:200]

        smtp.login(host_user, host_pass)
        smtp_debug["login"] = "ok"
        smtp.quit()
    except smtplib.SMTPAuthenticationError as e_auth:
        return Response({
            "ok": False,
            "stage": "smtp-auth",
            "error_type": "SMTPAuthenticationError",
            "smtp_code": e_auth.smtp_code,
            "smtp_error": (e_auth.smtp_error or b"").decode(errors="ignore"),
            "hint": "Gmail rechazó la autenticación. Si el app password es correcto y el usuario tiene 2FA, probablemente Google está bloqueando IPs de Railway → migrar a Resend.",
            "debug": smtp_debug,
            **info,
        }, status=500)
    except Exception as e_smtp:
        return Response({
            "ok": False,
            "stage": "smtp-handshake",
            "error_type": type(e_smtp).__name__,
            "error": str(e_smtp),
            "traceback": traceback.format_exc()[-1500:],
            "hint": "Falló el handshake SSL/TLS con Gmail. Probablemente Railway bloquea → migrar a Resend.",
            "debug": smtp_debug,
            **info,
        }, status=500)

    # 3) Si llegamos acá, SMTP está OK. Enviamos el mail real.
    try:
        connection = get_connection(
            backend="django.core.mail.backends.smtp.EmailBackend",
            host=host, port=port,
            username=host_user, password=host_pass,
            use_ssl=use_ssl, use_tls=use_tls,
            fail_silently=False,
            timeout=30,
        )
        msg = EmailMultiAlternatives(
            subject="LeadBook — prueba de email (debug)",
            body="Este es un email de prueba enviado por /api/v1/debug/email-send/.\nSi lo estás leyendo, SMTP funciona desde este servidor.",
            from_email=from_addr,
            to=[destino],
            connection=connection,
        )
        msg.attach_alternative(
            "<p>Este es un email de prueba enviado por <code>/api/v1/debug/email-send/</code>.</p>"
            "<p>Si lo estás leyendo, <b>SMTP funciona</b> desde este servidor.</p>",
            "text/html",
        )
        sent = msg.send(fail_silently=False)
        return Response({
            "ok": True,
            "stage": "sent",
            "sent_count": sent,
            "debug": smtp_debug,
            **info,
            "nota": "Si 'sent_count'=1 Gmail aceptó el mensaje. Revisá inbox y spam del destino.",
        })
    except Exception as e_send:
        return Response({
            "ok": False,
            "stage": "send-message",
            "error_type": type(e_send).__name__,
            "error": str(e_send),
            "traceback": traceback.format_exc()[-1500:],
            "debug": smtp_debug,
            **info,
        }, status=500)


@api_view(['GET'])
@permission_classes([AllowAny])
def proxy_pdf_view(request, listado_id):
    """
    Sirve el PDF desde Cloudinary actuando como proxy para evitar errores 401/ACL.
    Si el PDF es local (fallback), redirige a la URL local.
    """
    try:
        from .models import Listado
        listado = Listado.objects.get(id=listado_id)
        
        # Buscar URL en los datos del listado
        res = listado.datos.get('resultados', {}) if listado.datos else {}
        pdf_data = res.get('pdf', {})
        pdf_url = pdf_data.get('url') if isinstance(pdf_data, dict) else pdf_data
        
        if not pdf_url:
            return Response({"error": "URL de PDF no encontrada"}, status=404)

        # Si es URL local, redirigir directamente al endpoint que sirve el archivo
        if not pdf_url.startswith('http'):
            from django.shortcuts import redirect
            absolute_url = request.build_absolute_uri(pdf_url)
            if 'localhost' not in absolute_url and '127.0.0.1' not in absolute_url:
                absolute_url = absolute_url.replace('http://', 'https://')
            return redirect(absolute_url)

        # Petición interna a Cloudinary
        response = requests.get(pdf_url, stream=True, timeout=30)
        
        if response.status_code != 200:
            return Response({
                "error": f"Cloudinary respondió con error {response.status_code}"
            }, status=status.HTTP_502_BAD_GATEWAY)

        django_response = StreamingHttpResponse(
            response.iter_content(chunk_size=8192),
            content_type='application/pdf'
        )
        django_response['Content-Disposition'] = f'inline; filename="ficha_leadbook_{listado_id}.pdf"'
        return django_response

    except Listado.DoesNotExist:
        return Response({"error": "Listado no encontrado"}, status=404)
    except Exception as e:
        return Response({"error": str(e)}, status=500)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def descargar_pdf(request, listado_id):
    try:
        from .models import Listado
        from django.http import HttpResponse
        from django.shortcuts import get_object_or_404
        listado = get_object_or_404(Listado, id=listado_id, agente=request.user)
        datos = listado.datos or {}
        pdf_data = datos.get('resultados', {}).get('pdf', {})
        html_content = pdf_data.get('html', '') if isinstance(pdf_data, dict) else ''
        if not html_content:
            return Response({"error": "No hay PDF generado para este listado"}, status=404)
        from api.services.render_engine import render_html_to_pdf
        pdf_bytes = render_html_to_pdf(html_content)
        if not pdf_bytes:
            return Response({"error": "Error al generar PDF"}, status=500)
        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="ficha_leadbook_{listado_id}.pdf"'
        response['Access-Control-Allow-Origin'] = '*'
        return response
    except Listado.DoesNotExist:
        return Response({"error": "Listado no encontrado"}, status=404)
    except Exception as e:
        logger.error(f"Error en descargar_pdf: {e}")
        return Response({"error": str(e)}, status=500)

@api_view(['GET'])
@permission_classes([AllowAny])
def proxy_pdf_thumbnail_view(request, listado_id):
    """
    Genera una vista previa (imagen) de la primera página del PDF vía proxy.
    """
    try:
        from .models import Listado
        listado = Listado.objects.get(id=listado_id)
        res = listado.datos.get('resultados', {}) if listado.datos else {}
        pdf_data = res.get('pdf', {})
        pdf_url = pdf_data.get('url') if isinstance(pdf_data, dict) else pdf_data

        if not pdf_url or not pdf_url.startswith('http') or 'res.cloudinary.com' not in pdf_url:
            from django.shortcuts import redirect
            return redirect('https://placehold.co/400x600/111111/FFFFFF/png?text=Vista+Previa\\nNo+Disponible')

        thumb_url = pdf_url.replace('.pdf', '.jpg')
        if '/upload/' in thumb_url:
            thumb_url = thumb_url.replace('/upload/', '/upload/w_600,h_800,c_fill,pg_1/')

        response = requests.get(thumb_url, stream=True, timeout=15)
        
        if response.status_code != 200:
            return Response({"error": "No se pudo generar miniatura"}, status=404)

        return StreamingHttpResponse(
            response.iter_content(chunk_size=8192),
            content_type='image/jpeg'
        )

    except Exception as e:
        return Response({"error": str(e)}, status=500)

from django.shortcuts import get_object_or_404
from django.http import HttpResponse

@api_view(['GET'])
def generar_html(request, pk):
    from .models import Listado
    listado = get_object_or_404(Listado, pk=pk)
    data = listado.datos or {}
    context, temp_files, _, _, _ = construir_contexto_pdf(data, listado.agente, request)
    
    from django.template.loader import render_to_string
    try:
        html_string = render_to_string('pdf/property_brochure_html.html', context)
        # Limpiar temp files ya que no generamos PDF
        import os
        for f in temp_files:
            try:
                if os.path.exists(f):
                    os.remove(f)
            except Exception:
                pass
        return HttpResponse(html_string, content_type='text/html')
    except Exception as e:
        import traceback
        for f in temp_files:
            try:
                if os.path.exists(f):
                    os.remove(f)
            except Exception:
                pass
        return HttpResponse(f"Error generando HTML: {str(e)}<br><pre>{traceback.format_exc()}</pre>", content_type='text/html', status=500)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generar_escena(request):
    """Regenera el texto de UNA escena específica usando el mismo tono/voz del usuario."""
    data = request.data
    nombre_escena = data.get('nombre_escena', 'Escena')
    indice_escena = data.get('indice_escena', 0)
    total_escenas = data.get('total_escenas', 4)

    tipo = data.get('tipoPropiedad', 'Propiedad')
    ciudad = data.get('ciudad', '')
    operacion = data.get('operacion', 'Venta')
    moneda = data.get('moneda', 'USD')
    precio = data.get('precio', '')
    voz = data.get('voz', 'femenina')
    tono = data.get('tono', 'profesional')
    tipo_video = data.get('tipoVideo', 'reel')
    contexto_adicional = data.get('contextoAdicional', '')

    tono_map = {
        'profesional': 'profesional y formal, transmite confianza',
        'lujo': 'de lujo y exclusividad, sofisticado, usa vocabulario refinado',
        'energetico': 'dinámico y energético, usa frases cortas e impactantes',
    }
    tono_instrucciones = tono_map.get(tono, tono_map['profesional'])
    narrador = 'firme, directo, con autoridad' if voz == 'masculina' else 'cálido, cercano, invitador'
    palabras = '25-38' if tipo_video == 'reel' else '50-75'
    contexto_extra = f"\nEnfoque adicional: {contexto_adicional}" if contexto_adicional else ''

    prompt = f"""Sos un copywriter inmobiliario experto.
Generá SOLO el texto para la escena "{nombre_escena}" (escena {indice_escena + 1} de {total_escenas}) de un video inmobiliario.

PROPIEDAD: {tipo} en {operacion} | {ciudad} | {moneda} {precio}
TONO: {tono_instrucciones}
NARRADOR: {narrador}{contexto_extra}

REQUISITOS:
- Exactamente {palabras} palabras
- El texto es para narración en voz en off, debe sonar natural al hablar
- No pongas el nombre de la escena, solo el texto a narrar
- Responde SOLO el texto, sin JSON, sin comillas, sin explicaciones"""

    try:
        result = call_gemini_api(prompt, agente=request.user)
        if not result:
            return Response({"error": "No se pudo generar texto"}, status=503)
        return Response({"texto": result.strip()})
    except Exception as e:
        return Response({"error": str(e)}, status=500)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def upload_fotos_listado(request):
    """
    Sube fotos de propiedad (portada y galería) a Cloudinary a través del pool del backend.
    """
    data = request.data
    portada_b64 = data.get('portadaUrl')
    fotos_b64 = data.get('fotosRecorrido', [])
    listado_id = data.get('listado_id')

    user_id = request.user.id
    response_data = {
        'portadaUrl': None,
        'fotosRecorrido': []
    }

    try:
        from api.services.almacenamiento import AlmacenamientoCloudinary
        
        if portada_b64 and isinstance(portada_b64, str) and portada_b64.startswith('data:image'):
            print(f"[UPLOAD] portada_b64 tipo: {type(portada_b64).__name__}, es base64: {bool(portada_b64 and isinstance(portada_b64, str) and portada_b64.startswith('data:image'))}")
            obj = AlmacenamientoCloudinary.guardar_foto_propiedad(portada_b64, user_id, listado_id, tipo_foto='portada')
            print(f"[UPLOAD] get_mejor_cuenta resultado: {AlmacenamientoCloudinary.get_mejor_cuenta()}")
            print(f"[UPLOAD] resultado upload portada: {obj}")
            if obj:
                response_data['portadaUrl'] = obj
            else:
                response_data['portadaUrl'] = portada_b64 # Fallback
        elif isinstance(portada_b64, dict):
            response_data['portadaUrl'] = portada_b64
        elif portada_b64 and isinstance(portada_b64, str) and portada_b64.startswith('http'):
            response_data['portadaUrl'] = portada_b64
            
        for i, foto in enumerate(fotos_b64):
            if foto and isinstance(foto, str) and foto.startswith('data:image'):
                obj = AlmacenamientoCloudinary.guardar_foto_propiedad(foto, user_id, listado_id, tipo_foto='galeria', indice=i)
                if obj:
                    response_data['fotosRecorrido'].append(obj)
            elif isinstance(foto, dict):
                response_data['fotosRecorrido'].append(foto)
            elif foto and isinstance(foto, str) and foto.startswith('http'):
                response_data['fotosRecorrido'].append(foto)

        return Response(response_data)
        
    except Exception as e:
        logger.error(f"Error al subir fotos de listado: {e}")
        return Response({"error": str(e)}, status=500)
    except Exception as e:
        return Response({"error": str(e)}, status=500)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def listar_notificaciones(request):
    from .models import Notificacion
    notifs = Notificacion.objects.filter(usuario=request.user)[:20]
    data = [{
        'id': n.id,
        'tipo': n.tipo,
        'titulo': n.titulo,
        'mensaje': n.mensaje,
        'leida': n.leida,
        'creada_en': n.creada_en.isoformat(),
    } for n in notifs]
    no_leidas = Notificacion.objects.filter(usuario=request.user, leida=False).count()
    return Response({'notificaciones': data, 'no_leidas': no_leidas})

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def marcar_notificacion_leida(request, notif_id):
    from .models import Notificacion
    notif = Notificacion.objects.filter(id=notif_id, usuario=request.user).first()
    if notif:
        notif.leida = True
        notif.save()
    return Response({'ok': True})

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def marcar_todas_leidas(request):
    from .models import Notificacion
    Notificacion.objects.filter(usuario=request.user, leida=False).update(leida=True)
    return Response({'ok': True})

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def estado_cuota_ia(request):
    from .models import UserAPIQuota, Suscripcion
    try:
        quota = UserAPIQuota.objects.get(user=request.user, service='gemini')
        agotada = quota.is_blocked
        usado = quota.requests_today
        limite = quota.daily_limit
    except UserAPIQuota.DoesNotExist:
        agotada = False
        usado = 0
        limite = 1500
    
    try:
        suscripcion = request.user.suscripcion
        ai_used = suscripcion.ai_used
    except:
        ai_used = usado

    return Response({
        'agotada': agotada,
        'usado': ai_used,
        'limite': limite,
        'porcentaje': min(100, int((ai_used / limite) * 100)) if limite > 0 else 0
    })

@api_view(['GET', 'POST'])
@permission_classes([AllowAny])
def debug_quota(request):
    from .models import UserAPIQuota, APIKey, APIBundleAssignment
    
    if request.method == 'POST':
        from .models import UserAPIQuota
        # Desbloquear todos los usuarios cuyo uso actual es menor al límite
        desbloqueados = 0
        for q in UserAPIQuota.objects.filter(is_blocked=True):
            if q.requests_today < q.daily_limit:
                q.is_blocked = False
                q.save()
                desbloqueados += 1
        # Corregir límites incorrectos por servicio
        UserAPIQuota.objects.filter(service='uploadpost', daily_limit__gt=100).update(daily_limit=10)
        UserAPIQuota.objects.filter(service='gemini', daily_limit__lt=100).update(daily_limit=1500)
        
        # Reset extras de prueba (pago_id = 'manual_admin')
        from .models import BundleAPIExtra
        extras_borradas = BundleAPIExtra.objects.filter(pago_id='manual_admin').delete()
        print(f"[DEBUG] Extras de prueba borradas: {extras_borradas}")
        
        return Response({'desbloqueados': desbloqueados})
    
    quotas = list(UserAPIQuota.objects.values(
        'user_id', 'service', 'daily_limit', 'monthly_limit', 
        'requests_today', 'is_blocked'
    ))
    assignments = APIBundleAssignment.objects.filter(activo=True).select_related('usuario', 'bundle__key_gemini')
    keys_info = []
    for a in assignments:
        k = a.bundle.key_gemini if a.bundle else None
        if k:
            keys_info.append({
                'user': a.usuario.email,
                'key_id': k.id,
                'daily_limit': k.daily_limit,
                'monthly_limit': k.monthly_limit,
                'status': k.status
            })
    return Response({'quotas': quotas, 'keys': keys_info})

```

### File: api/views_admin.py
```python
# REBUILD FORCED - v2
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from decouple import config

ADMIN_KEY = config('ADMIN_KEY', default='')
from .models import Agent, Listado, Plan, APIKey, APIBundle, APIBundleAssignment, AdminAlert
from django.utils.timezone import now
from datetime import timedelta
from django.db.models import Count, Sum, Q

def _is_staff_check(request):
    if request.headers.get('X-Admin-Key') == ADMIN_KEY and ADMIN_KEY != '':
        return True
    return request.user and request.user.is_authenticated and request.user.is_staff

@api_view(['GET'])
@permission_classes([AllowAny])
def admin_metricas(request):
    if not _is_staff_check(request):
        return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)

    hoy = now().date()
    inicio_mes = hoy.replace(day=1)

    total_usuarios = Agent.objects.count()
    # Usuarios activos mes: usuarios que se loguearon este mes
    usuarios_activos_mes = Agent.objects.filter(last_login__date__gte=inicio_mes).count()
    total_listados = Listado.objects.count()
    listados_hoy = Listado.objects.filter(creado_en__date=hoy).count()

    # Ingresos mes estimado (MRR simplificado basándose en planes activos)
    ingresos = 0
    planes = Plan.objects.all()
    for p in planes:
        count = Agent.objects.filter(plan_nombre=p.nombre, plan_activo=True).count()
        ingresos += (count * float(p.precio_usd))

    usuarios_por_plan = {"free": 0, "starter": 0, "pro": 0, "scale": 0, "business": 0}
    stats_planes = Agent.objects.values('plan_nombre').annotate(total=Count('id'))
    for s in stats_planes:
        nombre = s['plan_nombre']
        if nombre in usuarios_por_plan:
            usuarios_por_plan[nombre] = s['total']

    return Response({
        "total_usuarios": total_usuarios,
        "usuarios_activos_mes": usuarios_activos_mes,
        "total_listados": total_listados,
        "listados_hoy": listados_hoy,
        "ingresos_mes": round(ingresos, 2),
        "usuarios_por_plan": usuarios_por_plan,
        # Compatibilidad con dashboard viejo
        "activos_hoy": Agent.objects.filter(last_login__gte=now()-timedelta(hours=24)).count(),
        "nuevos_hoy": Agent.objects.filter(fecha_registro__gte=now()-timedelta(hours=24)).count(),
        "distribucion_planes": usuarios_por_plan
    })

@api_view(['GET'])
@permission_classes([AllowAny])
def admin_usuarios_list(request):
    if not _is_staff_check(request):
        return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)

    from django.core.paginator import Paginator
    page_num = int(request.query_params.get('page', 1))
    page_size = int(request.query_params.get('page_size', 50))
    search = request.query_params.get('search', '')

    agentes = Agent.objects.filter(eliminado_en__isnull=True).order_by('-fecha_registro')
    
    if search:
        agentes = agentes.filter(
            Q(email__icontains=search) | Q(nombre__icontains=search)
        )

    paginator = Paginator(agentes, page_size)
    page = paginator.get_page(page_num)

    data = []
    for agente in page:
        data.append({
            'id': agente.id,
            'email': agente.email,
            'nombre': agente.nombre,
            'plan_nombre': agente.plan_nombre or 'free',
            'fecha_registro': agente.fecha_registro.isoformat() if agente.fecha_registro else None,
            'total_listados': Listado.objects.filter(agente=agente).count(),
            'ultimo_acceso': agente.last_login.isoformat() if agente.last_login else None,
            'is_active': agente.is_active
        })

    return Response({
        'total': paginator.count,
        'usuarios': data
    })

@api_view(['GET'])
@permission_classes([AllowAny])
def admin_usuarios_eliminados(request):
    if not _is_staff_check(request):
        return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
    
    agentes = Agent.objects.filter(eliminado_en__isnull=False).order_by('-eliminado_en')
    data = []
    for a in agentes:
        data.append({
            'id': a.id,
            'email': a.email,
            'nombre': a.nombre,
            'eliminado_en': a.eliminado_en.isoformat() if a.eliminado_en else None,
            'is_active': a.is_active
        })
    return Response({'usuarios': data})

@api_view(['POST'])
@permission_classes([AllowAny])
def admin_usuario_restaurar(request, user_id):
    if not _is_staff_check(request):
        return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
    try:
        agente = Agent.objects.get(id=user_id)
        agente.eliminado_en = None
        agente.is_active = True
        agente.save()
        return Response({'success': True, 'message': 'Usuario restaurado correctamente'})
    except Agent.DoesNotExist:
        return Response({'error': 'Usuario no encontrado'}, status=status.HTTP_404_NOT_FOUND)

@api_view(['POST'])
@permission_classes([AllowAny])
def admin_usuario_suspender(request, user_id):
    if not _is_staff_check(request):
        return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
    try:
        agente = Agent.objects.get(id=user_id)
        agente.is_active = not agente.is_active
        agente.save()
        estado = "suspendido" if not agente.is_active else "reactivado"
        return Response({'success': True, 'is_active': agente.is_active, 'estado': estado})
    except Agent.DoesNotExist:
        return Response({'error': 'Usuario no encontrado'}, status=status.HTTP_404_NOT_FOUND)

@api_view(['PUT'])
@permission_classes([AllowAny])
def admin_usuario_cambiar_plan(request, user_id):
    if not _is_staff_check(request):
        return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)

    nuevo_plan = request.data.get('plan')
    valid_plans = ['free', 'starter', 'pro', 'scale', 'business']
    if nuevo_plan not in valid_plans:
        return Response({'error': f'Plan inválido. Debe ser uno de: {", ".join(valid_plans)}'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        agente = Agent.objects.get(id=user_id)
        agente.plan_nombre = nuevo_plan
        agente.plan_activo = True # Se asume que si el admin lo cambia, queda activo
        agente.save()
        return Response({'success': True, 'id': agente.id, 'plan': nuevo_plan})
    except Agent.DoesNotExist:
        return Response({'error': 'Usuario no encontrado'}, status=status.HTTP_404_NOT_FOUND)

@api_view(['DELETE'])
@permission_classes([AllowAny])
def admin_usuario_eliminar(request, user_id):
    """Soft delete: marca eliminado_en y desactiva"""
    if not _is_staff_check(request):
        return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)

    try:
        agente = Agent.objects.get(id=user_id)
        email = agente.email
        agente.is_active = False
        agente.eliminado_en = now()
        agente.save()
        
        # Liberar APIs atadas a esta cuenta
        from api.services.pool_service import APIPoolService
        APIPoolService.release_keys_from_user(agente)

        # Trazabilidad
        AdminAlert.objects.create(
            type='system',
            severity='info',
            title='Usuario Desactivado y APIs Liberadas',
            message=f"El usuario {email} fue marcado como eliminado (soft-delete). Sus llaves API han sido regresadas al pool."
        )
        
        return Response({'success': True, 'eliminado': email, 'message': 'Usuario marcado como eliminado (soft delete)'})
    except Agent.DoesNotExist:
        return Response({'error': 'Usuario no encontrado'}, status=status.HTTP_404_NOT_FOUND)

@api_view(['GET'])
@permission_classes([AllowAny])
def admin_usuario_detalle(request, user_id):
    if not _is_staff_check(request):
        return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)

    try:
        agente = Agent.objects.get(id=user_id)
        listados = Listado.objects.filter(agente=agente).order_by('-creado_en')
        
        listados_data = []
        for l in listados:
            listados_data.append({
                "id": l.id,
                "titulo": l.titulo,
                "tipo": l.tipo_propiedad,
                "fecha": l.creado_en.isoformat() if l.creado_en else None,
                "video": l.video_status != 'none'
            })
            
        return Response({
            "usuario": {
                "id": agente.id,
                "email": agente.email,
                "nombre": agente.nombre,
                "plan": agente.plan_nombre,
                "fecha_registro": agente.fecha_registro.isoformat() if agente.fecha_registro else None,
                "is_active": agente.is_active,
                "eliminado_en": agente.eliminado_en.isoformat() if agente.eliminado_en else None
            },
            "actividad": {
                "total_listados": listados.count(),
                "listados": listados_data
            }
        })
    except Agent.DoesNotExist:
        return Response({'error': 'Usuario no encontrado'}, status=status.HTTP_404_NOT_FOUND)

@api_view(['POST'])
@permission_classes([AllowAny])
def admin_enviar_email(request, user_id):
    if not _is_staff_check(request):
        return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
    try:
        agente = Agent.objects.get(id=user_id)
        asunto = request.data.get('asunto', 'Mensaje de LeadBook')
        mensaje = request.data.get('mensaje', '')
        if not mensaje:
            return Response({'error': 'Mensaje requerido'}, status=400)
        
        from django.core.mail import send_mail
        from django.conf import settings
        send_mail(
            subject=asunto,
            message=mensaje,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[agente.email],
            fail_silently=False
        )
        return Response({'success': True, 'message': f'Email enviado a {agente.email}'})
    except Agent.DoesNotExist:
        return Response({'error': 'Usuario no encontrado'}, status=404)
    except Exception as e:
        return Response({'error': str(e)}, status=500)

# --- API Keys & Pool ---

@api_view(['GET'])
@permission_classes([AllowAny])
def admin_apikeys_resumen(request):
    if not _is_staff_check(request):
        return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
    
    umbral = request.query_params.get('umbral_libres')
    
    total = APIKey.objects.count()
    por_servicio = APIKey.objects.values('servicio').annotate(
        total=Count('id'),
        disponibles=Count('id', filter=Q(status='available')),
        agotadas=Count('id', filter=Q(status='exhausted'))
    )
    
    if umbral is not None:
        return Response(list(por_servicio))
        
    estado_pool = APIKey.objects.values('status').annotate(total=Count('id'))
    
    return Response({
        "total": total,
        "por_servicio": list(por_servicio),
        "estados": list(estado_pool)
    })

@api_view(['GET'])
def admin_apikeys_pool(request):
    if not _is_staff_check(request):
        return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
    
    from .models import BundleAPIExtra, UserAPIQuota
    
    servicio = request.query_params.get('servicio')
    keys = APIKey.objects.all().select_related('assigned_to').order_by('servicio', '-created_at')
    if servicio:
        keys = keys.filter(servicio__icontains=servicio)
    
    DEFAULT_LIMITS = {'gemini': 1500, 'elevenlabs': 10000, 'uploadpost': 10}
    
    data = []
    for k in keys:
        limite = k.monthly_limit or DEFAULT_LIMITS.get(k.servicio, 100)
        consumo = k.requests_this_month or 0
        porcentaje = min(100, int((consumo / limite) * 100)) if limite else 0
        
        user_daily_used = k.requests_today or 0
        user_daily_limit = k.daily_limit or DEFAULT_LIMITS.get(k.servicio, 1500)
        user_is_blocked = False
        extras_list = []
        
        # Obtener user_id — directo o via bundle
        assigned_user_id = k.assigned_to_id
        if not assigned_user_id:
            from .models import APIBundleAssignment
            svc = k.servicio
            bundle_asig = None
            if svc == 'gemini':
                bundle_asig = APIBundleAssignment.objects.filter(activo=True, bundle__key_gemini=k).first()
            elif svc == 'elevenlabs':
                bundle_asig = APIBundleAssignment.objects.filter(activo=True, bundle__key_elevenlabs=k).first()
            elif svc == 'uploadpost':
                bundle_asig = APIBundleAssignment.objects.filter(activo=True, bundle__key_uploadpost=k).first()
            if bundle_asig:
                assigned_user_id = bundle_asig.usuario_id
        
        # Cruzar con UserAPIQuota y BundleAPIExtra
        if assigned_user_id:
            q = UserAPIQuota.objects.filter(user_id=assigned_user_id, service=k.servicio).first()
            if q:
                user_daily_used = q.requests_today or 0
                user_daily_limit = q.daily_limit or DEFAULT_LIMITS.get(k.servicio, 1500)
                user_is_blocked = q.is_blocked or False
                if user_is_blocked:
                    user_daily_used = user_daily_limit
                    porcentaje = 100
            
            extras_qs = BundleAPIExtra.objects.filter(
                usuario_id=assigned_user_id,
                servicio=k.servicio,
                activa=True
            ).select_related('api_key')
            
            extras_list = [{
                'id': e.id,
                'servicio': e.servicio,
                'api_key_preview': e.api_key.api_key[:10] + '...' if e.api_key else '',
                'comprada_en': e.comprada_en.strftime('%d/%m/%Y') if e.comprada_en else '',
                'pago_id': e.pago_id or '',
            } for e in extras_qs]
        
        data.append({
            'id': k.id,
            'servicio': k.servicio,
            'service': k.servicio,
            'status': k.status,
            'api_key': k.api_key,
            'key_masked': k.api_key[:10] + '...' if k.api_key else '',
            'assigned_to': k.assigned_to.email if k.assigned_to else None,
            'assigned_to_email': k.assigned_to.email if k.assigned_to else None,
            'assigned_to_id': assigned_user_id,
            'assigned_to_nombre': k.assigned_to.nombre if k.assigned_to else None,
            'requests_today': user_daily_used,
            'daily_limit': user_daily_limit,
            'requests_this_month': consumo,
            'monthly_limit': limite,
            'porcentaje_uso': porcentaje,
            'total_requests': k.total_requests or 0,
            'error_count': k.error_count or 0,
            'last_used': k.last_used_at.isoformat() if k.last_used_at else None,
            'last_health_status': k.last_health_status,
            'is_blocked': user_is_blocked,
            'extras': extras_list,
        })
    
    return Response(data)

@api_view(['POST'])
@permission_classes([AllowAny])
def admin_apikeys_pool_crear(request):
    if not _is_staff_check(request):
        return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
    
    servicio = request.data.get('servicio')
    api_key = request.data.get('api_key')
    daily_limit = request.data.get('daily_limit', 1500)
    if not servicio or not api_key:
        return Response({'error': 'Servicio y API Key son requeridos'}, status=400)
        
    k = APIKey.objects.create(
        servicio=servicio.lower() if isinstance(servicio, str) else servicio,
        api_key=api_key,
        status='available',
        daily_limit=daily_limit,
    )
    return Response({"success": True, "id": k.id})

@api_view(['POST'])
@permission_classes([AllowAny])
def admin_apikeys_pool_bulk(request):
    """
    Carga masiva de keys desde el dashboard.
    Mapea 'service' -> 'servicio' y 'key' -> 'api_key' para compatibilidad con el frontend.
    """
    if not _is_staff_check(request):
        return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
    
    keys_data = request.data.get('keys', [])
    creadas = 0
    for k in keys_data:
        # Usamos los nombres de campos que envía el frontend en ApiPoolPage.jsx
        service_val = k.get('service') or k.get('servicio', 'gemini')
        key_val = k.get('key') or k.get('api_key')
        
        if not key_val:
            continue

        APIKey.objects.create(
            api_key=key_val,
            servicio=service_val.lower().strip() if isinstance(service_val, str) else service_val,
            label=k.get('label', '-'),
            status='available',
            daily_limit=k.get('daily_limit', 1500),
            monthly_limit=k.get('monthly_limit', None),
        )
        creadas += 1
        
    return Response({
        'success': True, 
        'creadas': creadas, 
        'mensaje': f'{creadas} keys creadas exitosamente'
    })

@api_view(['POST'])
def admin_add_extra_api(request, user_id):
    if not _is_staff_check(request):
        return Response({'error': 'Forbidden'}, status=403)
    from .models import Agent, APIKey, BundleAPIExtra, UserAPIQuota
    servicio = request.data.get('servicio', 'gemini')
    try:
        agent = Agent.objects.get(id=user_id)
        keys_ya_usadas = BundleAPIExtra.objects.filter(
            usuario=agent, servicio=servicio, activa=True
        ).values_list('api_key_id', flat=True)
        key_disponible = APIKey.objects.filter(
            servicio=servicio, status__in=['available', 'active']
        ).exclude(id__in=keys_ya_usadas).first()
        
        if not key_disponible:
            # Intentar con keys exhausted también
            key_disponible = APIKey.objects.filter(
                servicio=servicio
            ).exclude(id__in=keys_ya_usadas).first()
            if not key_disponible:
                return Response({'error': 'No hay keys disponibles'}, status=400)
                
        print(f"[ADD EXTRA] user_id={user_id} servicio={servicio} key={key_disponible.api_key[:10] if key_disponible else 'NONE'}")
        
        BundleAPIExtra.objects.create(
            usuario=agent, api_key=key_disponible,
            servicio=servicio, activa=True, pago_id='manual_admin'
        )
        
        count = BundleAPIExtra.objects.filter(usuario=agent, servicio=servicio).count()
        print(f"[ADD EXTRA] Total extras para user {user_id}: {count}")
        
        quota, _ = UserAPIQuota.objects.get_or_create(user=agent, service=servicio)
        quota.is_blocked = False
        quota.daily_limit = (quota.daily_limit or 1500) + 1500
        quota.monthly_limit = (quota.monthly_limit or 1500) + 1500
        quota.save()
        return Response({'ok': True, 'key': key_disponible.api_key[:10] + '...'})
    except Agent.DoesNotExist:
        return Response({'error': 'Usuario no encontrado'}, status=404)

@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([AllowAny])
def admin_apikeys_pool_detail(request, key_id):
    if not _is_staff_check(request):
        return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
    
    try:
        k = APIKey.objects.get(id=key_id)
        if request.method == 'GET':
            return Response({
                "id": k.id,
                "servicio": k.servicio,
                "status": k.status,
                "api_key": k.api_key,
                "requests_today": k.requests_today,
                "error_count": k.error_count,
                "notes": k.notes
            })
        elif request.method == 'PUT':
            for attr, value in request.data.items():
                if hasattr(k, attr):
                    setattr(k, attr, value)
            k.save()
            return Response({"success": True})
        elif request.method == 'DELETE':
            k.delete()
            return Response({"success": True})
    except APIKey.DoesNotExist:
        return Response({'error': 'Key no encontrada'}, status=404)

@api_view(['GET', 'POST'])
@permission_classes([AllowAny])
def admin_apikeys_global(request):
    if not _is_staff_check(request):
        return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
    # Placeholder para configuraciones globales
    return Response({"message": "Settings globales no implementados"})

@api_view(['GET'])
@permission_classes([AllowAny])
def admin_pool_estado(request):
    if not _is_staff_check(request):
        return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
        
    servicios = APIKey.objects.values('servicio').annotate(
        total=Count('id'),
        disponibles=Count('id', filter=Q(status='available')),
        agotadas=Count('id', filter=Q(status='exhausted')),
        muertas=Count('id', filter=Q(status='dead'))
    )
    
    alertas_criticas = AdminAlert.objects.filter(is_read=False, severity='critical').count()
    
    if "pool/estado" in request.path:
        return Response(list(servicios))

    return Response({
        "servicios": servicios,
        "alertas_criticas": alertas_criticas,
        "estado_general": "OK" if alertas_criticas == 0 else "WARNING"
    })

@api_view(['POST'])
@permission_classes([AllowAny])
def admin_alerts_read(request, alert_id):
    if not _is_staff_check(request):
        return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
    try:
        alerta = AdminAlert.objects.get(id=alert_id)
        alerta.is_read = True
        alerta.save()
        return Response({"success": True})
    except AdminAlert.DoesNotExist:
        return Response({'error': 'Alerta no encontrada'}, status=404)

@api_view(['POST'])
@permission_classes([AllowAny])
def admin_health_check(request):
    if not _is_staff_check(request):
        return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
    
    # Aquí iría el disparador de la tarea de health check
    # Por ahora devolvemos éxito simulado
    return Response({"success": True, "message": "Health check iniciado"})


# ── Bundle endpoints ──────────────────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([AllowAny])
def admin_bundles_list(request):
    """Lista todos los bundles con su estado y usuario asignado."""
    if not _is_staff_check(request):
        return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)

    bundles = APIBundle.objects.prefetch_related('assignments__usuario').select_related(
        'key_gemini', 'key_elevenlabs', 'key_uploadpost'
    ).all().order_by('-created_at')

    data = []
    for b in bundles:
        asig_activa = b.assignments.filter(activo=True).select_related('usuario').first()
        data.append({
            'id': b.id,
            'nombre': b.nombre,
            'status': b.status,
            'is_complete': b.is_complete(),
            'notas': b.notas,
            'key_gemini': b.key_gemini.label if b.key_gemini else None,
            'key_elevenlabs': b.key_elevenlabs.label if b.key_elevenlabs else None,
            'key_uploadpost': b.key_uploadpost.label if b.key_uploadpost else None,
            'usuario_asignado': {
                'id': asig_activa.usuario.id,
                'email': asig_activa.usuario.email,
                'nombre': asig_activa.usuario.nombre,
                'asignado_en': asig_activa.asignado_en.isoformat(),
            } if asig_activa else None,
            'created_at': b.created_at.isoformat(),
        })
    return Response({'bundles': data})


@api_view(['POST'])
@permission_classes([AllowAny])
def admin_bundles_crear(request):
    """Crea un nuevo bundle y opcionalmente lo asigna a un usuario."""
    if not _is_staff_check(request):
        return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)

    nombre = request.data.get('nombre')
    if not nombre:
        return Response({'error': 'El campo nombre es requerido'}, status=400)

    key_gemini_id = request.data.get('key_gemini_id')
    key_elevenlabs_id = request.data.get('key_elevenlabs_id')
    key_uploadpost_id = request.data.get('key_uploadpost_id')
    notas = request.data.get('notas', '')

    bundle = APIBundle(nombre=nombre, notas=notas)
    if key_gemini_id:
        bundle.key_gemini_id = key_gemini_id
    if key_elevenlabs_id:
        bundle.key_elevenlabs_id = key_elevenlabs_id
    if key_uploadpost_id:
        bundle.key_uploadpost_id = key_uploadpost_id
    bundle.save()

    return Response({'success': True, 'id': bundle.id, 'nombre': bundle.nombre})


@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([AllowAny])
def admin_bundles_detail(request, bundle_id):
    """Detalle, edición y eliminación de un bundle."""
    if not _is_staff_check(request):
        return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)

    try:
        b = APIBundle.objects.get(id=bundle_id)
    except APIBundle.DoesNotExist:
        return Response({'error': 'Bundle no encontrado'}, status=404)

    if request.method == 'GET':
        asig_activa = b.assignments.filter(activo=True).select_related('usuario').first()
        return Response({
            'id': b.id,
            'nombre': b.nombre,
            'status': b.status,
            'notas': b.notas,
            'is_complete': b.is_complete(),
            'key_gemini_id': b.key_gemini_id,
            'key_elevenlabs_id': b.key_elevenlabs_id,
            'key_uploadpost_id': b.key_uploadpost_id,
            'usuario_asignado': {
                'id': asig_activa.usuario.id,
                'email': asig_activa.usuario.email,
            } if asig_activa else None,
        })

    elif request.method == 'PUT':
        for field in ['nombre', 'status', 'notas', 'key_gemini_id', 'key_elevenlabs_id', 'key_uploadpost_id']:
            if field in request.data:
                setattr(b, field, request.data[field])
        b.save()
        return Response({'success': True})

    elif request.method == 'DELETE':
        if b.assignments.filter(activo=True).exists():
            return Response({'error': 'No se puede eliminar un bundle con usuarios activos'}, status=400)
        b.delete()
        return Response({'success': True})


@api_view(['POST'])
@permission_classes([AllowAny])
def admin_bundles_asignar(request, bundle_id):
    """Asigna manualmente un bundle a un usuario específico."""
    if not _is_staff_check(request):
        return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)

    usuario_id = request.data.get('usuario_id')
    if not usuario_id:
        return Response({'error': 'usuario_id es requerido'}, status=400)

    try:
        bundle = APIBundle.objects.get(id=bundle_id)
        usuario = Agent.objects.get(id=usuario_id)
    except (APIBundle.DoesNotExist, Agent.DoesNotExist) as e:
        return Response({'error': str(e)}, status=404)

    # Liberar bundle anterior si tiene
    APIBundleAssignment.objects.filter(usuario=usuario, activo=True).update(
        activo=False
    )

    bundle.status = 'assigned'
    bundle.save(update_fields=['status'])

    asig, _ = APIBundleAssignment.objects.get_or_create(
        bundle=bundle,
        usuario=usuario,
        defaults={'activo': True}
    )
    asig.activo = True
    asig.save()

    return Response({'success': True, 'bundle': bundle.nombre, 'usuario': usuario.email})


@api_view(['POST'])
@permission_classes([AllowAny])
def admin_bundles_liberar(request, bundle_id):
    """Libera un bundle de su usuario actual."""
    if not _is_staff_check(request):
        return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)

    from django.utils import timezone as tz
    try:
        bundle = APIBundle.objects.get(id=bundle_id)
    except APIBundle.DoesNotExist:
        return Response({'error': 'Bundle no encontrado'}, status=404)

    asig = bundle.assignments.filter(activo=True).first()
    if asig:
        asig.activo = False
        asig.liberado_en = tz.now()
        asig.save()

    bundle.status = 'available'
    bundle.save(update_fields=['status'])
    return Response({'success': True, 'message': 'Bundle liberado correctamente'})


@api_view(['GET'])
@permission_classes([AllowAny])
def admin_bundles_stats(request):
    """Estadísticas rápidas del pool de bundles."""
    if not _is_staff_check(request):
        return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)

    from .services.pool_service import APIPoolService
    return Response(APIPoolService.get_pool_stats())


# ─── Librería de Audio (VideoMusic + VideoSFX) ───────────────────────────────

@api_view(['GET', 'POST'])
@permission_classes([AllowAny])
def admin_audio_music(request):
    """Lista o sube música de fondo para los videos."""
    if not _is_staff_check(request):
        return Response({'error': 'Forbidden'}, status=403)

    from .models import VideoMusic
    if request.method == 'GET':
        tracks = VideoMusic.objects.all().order_by('-creado_en')
        data = [{
            'id': t.id,
            'nombre': t.nombre,
            'duracion_segundos': t.duracion_segundos,
            'activo': t.activo,
            'url': request.build_absolute_uri(t.archivo.url) if t.archivo else None,
            'creado_en': t.creado_en,
        } for t in tracks]
        return Response(data)

    # POST: subir nueva pista
    archivo = request.FILES.get('archivo')
    nombre = request.data.get('nombre', archivo.name if archivo else 'Sin nombre')
    duracion = request.data.get('duracion_segundos', 0)
    if not archivo:
        return Response({'error': 'No se envió archivo'}, status=400)
    track = VideoMusic.objects.create(nombre=nombre, archivo=archivo, duracion_segundos=duracion)
    return Response({'success': True, 'id': track.id, 'nombre': track.nombre}, status=201)


@api_view(['DELETE', 'PATCH'])
@permission_classes([AllowAny])
def admin_audio_music_detail(request, pk):
    """Elimina o activa/desactiva una pista de música."""
    if not _is_staff_check(request):
        return Response({'error': 'Forbidden'}, status=403)
    from .models import VideoMusic
    try:
        track = VideoMusic.objects.get(pk=pk)
    except VideoMusic.DoesNotExist:
        return Response({'error': 'No encontrado'}, status=404)

    if request.method == 'DELETE':
        track.archivo.delete(save=False)
        track.delete()
        return Response({'success': True})

    # PATCH: toggle activo
    track.activo = not track.activo
    track.save(update_fields=['activo'])
    return Response({'success': True, 'activo': track.activo})


@api_view(['GET', 'POST'])
@permission_classes([AllowAny])
def admin_audio_sfx(request):
    """Lista o sube efectos de sonido (SFX)."""
    if not _is_staff_check(request):
        return Response({'error': 'Forbidden'}, status=403)

    from .models import VideoSFX
    if request.method == 'GET':
        sfx_list = VideoSFX.objects.all().order_by('-creado_en')
        data = [{
            'id': s.id,
            'nombre': s.nombre,
            'tipo': s.tipo,
            'activo': s.activo,
            'url': request.build_absolute_uri(s.archivo.url) if s.archivo else None,
            'creado_en': s.creado_en,
        } for s in sfx_list]
        return Response(data)

    # POST: subir nuevo SFX
    archivo = request.FILES.get('archivo')
    nombre = request.data.get('nombre', archivo.name if archivo else 'Sin nombre')
    tipo = request.data.get('tipo', 'other')
    if not archivo:
        return Response({'error': 'No se envió archivo'}, status=400)
    sfx = VideoSFX.objects.create(nombre=nombre, tipo=tipo, archivo=archivo)
    return Response({'success': True, 'id': sfx.id, 'nombre': sfx.nombre}, status=201)


@api_view(['DELETE', 'PATCH'])
@permission_classes([AllowAny])
def admin_audio_sfx_detail(request, pk):
    """Elimina o activa/desactiva un SFX."""
    if not _is_staff_check(request):
        return Response({'error': 'Forbidden'}, status=403)
    from .models import VideoSFX
    try:
        sfx = VideoSFX.objects.get(pk=pk)
    except VideoSFX.DoesNotExist:
        return Response({'error': 'No encontrado'}, status=404)

    if request.method == 'DELETE':
        sfx.archivo.delete(save=False)
        sfx.delete()
        return Response({'success': True})

    sfx.activo = not sfx.activo
    sfx.save(update_fields=['activo'])
    return Response({'success': True, 'activo': sfx.activo})

@api_view(['POST'])
@permission_classes([AllowAny])
def admin_apikeys_auto_repair(request):
    """
    Busca usuarios activos que tengan servicios faltantes o caídos 
    y les intenta asignar las faltantes del pool usando APIPoolService.
    """
    if not _is_staff_check(request):
        return Response({'error': 'Forbidden'}, status=403)
        
    from api.models import Agent
    from api.services.pool_service import APIPoolService
    
    # Podemos filtrar por IDs si se pasan en el request (para reparación selectiva)
    user_ids = request.data.get('user_ids', [])
    
    if user_ids:
        users = Agent.objects.filter(id__in=user_ids, is_active=True)
    else:
        # Por defecto repara a todos los activos
        users = Agent.objects.filter(is_active=True)
        
    fixed = 0
    details = []
    
    for user in users:
        repaired = APIPoolService.repair_user_apis(user)
        if repaired:
            fixed += 1
            details.append({"email": user.email, "repaired": repaired})
            
    return Response({"status": "success", "fixed_count": fixed, "details": details})
@api_view(['GET', 'POST'])
@permission_classes([AllowAny])
def admin_branding_watermark(request):
    if not _is_staff_check(request):
        return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)

    from .models import ConfiguracionSistema
    import base64
    from io import BytesIO
    import cloudinary.uploader
    from api.services.almacenamiento import AlmacenamientoCloudinary

    if request.method == 'GET':
        config, created = ConfiguracionSistema.objects.get_or_create(clave='watermark')
        url = config.datos.get('url') if config.datos else None
        return Response({
            'url': url,
            'actualizado_en': config.actualizado_en
        })

    if request.method == 'POST':
        image_base64 = request.data.get('image')
        if not image_base64:
            return Response({'error': 'Imagen requerida'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # Limpiar el prefijo data:image/png;base64, si existe
            if 'base64,' in image_base64:
                image_base64 = image_base64.split('base64,')[1]
            
            image_data = base64.b64decode(image_base64)
            image_stream = BytesIO(image_data)
            
            # Usar la mejor cuenta disponible del pool
            creds, key_id = AlmacenamientoCloudinary.get_mejor_cuenta()
            extra_creds = creds if creds else {}

            resultado = cloudinary.uploader.upload(
                image_stream,
                folder="leadbook/sistema",
                public_id="watermark",
                overwrite=True,
                invalidate=True,
                **extra_creds
            )

            url = resultado.get('secure_url')

            if not url:
                return Response({'error': 'Error al subir a Cloudinary'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            # Guardar en la configuración
            config, created = ConfiguracionSistema.objects.get_or_create(clave='watermark')
            config.datos = {
                'url': url,
                'public_id': resultado.get('public_id'),
                'cloud_name': extra_creds.get('cloud_name')
            }
            config.save()

            return Response({
                'message': 'Marca de agua actualizada exitosamente',
                'url': url
            })
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

```

### File: subzero_core/settings.py
```python
"""
Django settings for subzero_core project.

Generated by 'django-admin startproject' using Django 4.2.29.

For more information on this file, see
https://docs.djangoproject.com/en/4.2/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/4.2/ref/settings/
"""

import os
from pathlib import Path
from decouple import config

# Aumentar hilos para vistas síncronas largas (como Gemini)
os.environ.setdefault("ASGI_THREADS", "100")
import dj_database_url
import cloudinary
import cloudinary.uploader
import cloudinary.api

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/4.2/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = config('SECRET_KEY')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = config('DEBUG', default=False, cast=bool)

ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='*').split(',')

# Application definition

INSTALLED_APPS = [
    'daphne',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'cloudinary_storage',
    'django.contrib.staticfiles',
    
    # Third party
    'cloudinary',
    'rest_framework',
    'corsheaders',

    # Local
    'api',
    'admin_panel',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',
    'channels',
]

AUTH_USER_MODEL = 'api.Agent'

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'subzero_core.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'templates')],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'subzero_core.wsgi.application'
ASGI_APPLICATION = 'subzero_core.asgi.application'


# Database
# https://docs.djangoproject.com/en/4.2/ref/settings/#databases

_DATABASE_URL = config("DATABASE_URL", default="").strip()

if _DATABASE_URL:
    DATABASES = {
        'default': dj_database_url.config(
            default=_DATABASE_URL,
            conn_max_age=600,
            ssl_require=not DEBUG
        )
    }
else:
    # Ruta del SQLite: permite override por SQLITE_PATH (útil en filesystems
    # donde BASE_DIR no soporta locking, p.ej. algunos mounts virtuales).
    _sqlite_path = config('SQLITE_PATH', default=str(BASE_DIR / 'db.sqlite3'))
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': _sqlite_path,
            'OPTIONS': {'timeout': 20},
        }
    }


# Password validation
# https://docs.djangoproject.com/en/4.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/4.2/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/4.2/howto/static-files/

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
# STATICFILES_STORAGE = 'whitenoise.storage.CompressedStaticFilesStorage'
STATICFILES_STORAGE = 'django.contrib.staticfiles.storage.StaticFilesStorage'

MEDIA_URL = 'media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

# Default primary key field type
# https://docs.djangoproject.com/en/4.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'api.authentication.JWTAuthenticationFromQueryParam',
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    )
}

from datetime import timedelta
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(hours=8),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
}

# CORS Configuration
CORS_ALLOWED_ORIGINS_ENV = config('CORS_ALLOWED_ORIGINS', default='')
_env_origins = [o.strip() for o in CORS_ALLOWED_ORIGINS_ENV.split(',') if o.strip()]
_hardcoded_origins = [
    'https://dash-admin-leadbook.vercel.app',
    'https://leadbook.com.ar',
    'https://www.leadbook.com.ar',
    'http://localhost:5173',
    'http://localhost:4173',
    'http://localhost:3000',
]
CORS_ALLOWED_ORIGINS = list(dict.fromkeys(_env_origins + _hardcoded_origins))
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_HEADERS = [
    'accept', 'accept-encoding', 'authorization', 'content-type', 'dnt',
    'origin', 'user-agent', 'x-csrftoken', 'x-requested-with', 'x-admin-key',
]
CORS_ALLOW_METHODS = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS']
print(f"[STARTUP] CORS_ALLOWED_ORIGINS={CORS_ALLOWED_ORIGINS}")

CSRF_TRUSTED_ORIGINS = config('CSRF_TRUSTED_ORIGINS', default='https://dash-admin-leadbook.vercel.app').split(',')

# Celery Configuration
CELERY_BROKER_URL = config('REDIS_URL', default='redis://127.0.0.1:6379/0')
CELERY_RESULT_BACKEND = config('REDIS_URL', default='redis://127.0.0.1:6379/0')
# En local sin Redis, las tasks se ejecutan en línea (síncrono)
CELERY_TASK_ALWAYS_EAGER = config('CELERY_TASK_ALWAYS_EAGER', default=True, cast=bool)
CELERY_TASK_EAGER_PROPAGATES = True

# Cache Configuration — usa Redis si está disponible, sino memoria local
_REDIS_URL = config('REDIS_URL', default='')
if _REDIS_URL:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": _REDIS_URL,
        }
    }
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels_redis.core.RedisChannelLayer",
            "CONFIG": {
                "hosts": [_REDIS_URL],
            },
        },
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "leadbook-cache",
        }
    }
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels.layers.InMemoryChannelLayer"
        }
    }

# Cloudinary Configuration
import cloudinary

cloudinary.config(
    cloud_name=config('CLOUDINARY_CLOUD_NAME', default=''),
    api_key=config('CLOUDINARY_API_KEY', default=''),
    api_secret=config('CLOUDINARY_API_SECRET', default='')
)

VIDEO_ENGINE_DIR = os.path.join(BASE_DIR, 'hyperframes_engine')

# External APIs
GEMINI_API_KEY     = config('GEMINI_API_KEY', default='')
GROQ_API_KEY       = config('GROQ_API_KEY', default='')
ELEVENLABS_API_KEY = config('ELEVENLABS_API_KEY', default='')
UPLOADPOST_API_KEY = config('UPLOADPOST_API_KEY', default='')
NVIDIA_API_KEY     = config('NVIDIA_API_KEY', default='')

# MercadoPago Configuration
MP_ACCESS_TOKEN    = config('MP_ACCESS_TOKEN', default='')
MP_PUBLIC_KEY      = config('MP_PUBLIC_KEY', default='')
MP_WEBHOOK_SECRET  = config('MP_WEBHOOK_SECRET', default='')
BACKEND_URL        = config('BACKEND_URL', default='http://localhost:8000')
FRONTEND_URL       = config('FRONTEND_URL', default='http://localhost:5173')

# Email / SMTP Configuration
# Si no hay GMAIL_APP_PASSWORD se usa el console backend (OTP impreso por stdout).
EMAIL_HOST_USER     = config('GMAIL_USER', default='')
EMAIL_HOST_PASSWORD = config('GMAIL_APP_PASSWORD', default='')

if EMAIL_HOST_USER and EMAIL_HOST_PASSWORD:
    EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
    EMAIL_HOST    = 'smtp.gmail.com'
    EMAIL_PORT    = 465
    EMAIL_USE_TLS = False
    EMAIL_USE_SSL = True
    DEFAULT_FROM_EMAIL = f'LeadBook <{EMAIL_HOST_USER}>'
    print(f"[STARTUP] EMAIL_BACKEND=SMTP | host={EMAIL_HOST}:{EMAIL_PORT} | user={EMAIL_HOST_USER} | pass_len={len(EMAIL_HOST_PASSWORD)}")
else:
    # Fallback de desarrollo: imprime los emails en la consola
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
    EMAIL_HOST    = 'smtp.gmail.com'
    EMAIL_PORT    = 465
    EMAIL_USE_TLS = False
    EMAIL_USE_SSL = True
    DEFAULT_FROM_EMAIL = 'LeadBook <no-reply@leadbook.local>'
    print("[STARTUP] EMAIL_BACKEND=CONSOLE (falta GMAIL_USER o GMAIL_APP_PASSWORD en env) "
          f"GMAIL_USER_set={bool(EMAIL_HOST_USER)} GMAIL_APP_PASSWORD_set={bool(EMAIL_HOST_PASSWORD)}")

CLOUDINARY_STORAGE = {
    'CLOUD_NAME': config('CLOUDINARY_CLOUD_NAME', default=''),
    'API_KEY': config('CLOUDINARY_API_KEY', default=''),
    'API_SECRET': config('CLOUDINARY_API_SECRET', default='')
}

DEFAULT_FILE_STORAGE = 'cloudinary_storage.storage.MediaCloudinaryStorage'

X_FRAME_OPTIONS = 'SAMEORIGIN'

```

