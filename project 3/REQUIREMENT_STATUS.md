# مصفوفة المتطلبات والإثباتات — NovaMart

آخر مراجعة: 2026-10-22 بتوقيت Asia/Hebron (2026-10-21 UTC). المصادر الملزمة: `project_brief/01`–`07` و`starter/`. تقارير الشبكة القديمة محفوظة كتاريخ؛ الشبكة والمصادقة تعملان حاليًا.

**النتيجة الحالية:** AWS منشور، الاختبار الرسمي الكامل **120/120**، و43 اختبارًا محليًا ناجحًا. جولة Runtime أثبتت المسارات الثلاثة والذاكرة. التسليم النهائي **BLOCKED** حتى اكتمال مراجعة الصور المطلوبة. تصحيح صياغة Communication الأخير منشور على Runtime version 3 وتحقق فعليًا؛ `final-policy-grounding.json` يثبت المصادر وعدم افتراض tier.

الحالات: **IMPLEMENTED** تنفيذ موجود دون إثبات تشغيل كافٍ؛ **VERIFIED** تحقق بالطريقة المحددة؛ **BLOCKED** يتطلب تدخلًا خارجيًا؛ **NOT COMPLETED** غير منجز. الاختبارات المحلية تستخدم doubles ولا تُعرض كإثبات AWS.

| ID | معيار Rubric | موقع التنفيذ | التحقق والدليل الفعلي | الحالة | المتبقي |
|---|---|---|---|---|---|
| A01 | Inventory يعيد Strands Agent وثلاث أدوات lookup/tier/orders | `starter/src/agent_orchestrator.py:build_inventory_agent` | official task2 ضمن `official-all.log`؛ Runtime return | VERIFIED | — |
| A02 | مفتاح Orders المركب customer_id + order_id | `check_order_status` | local composite-key test؛ lookup فعلي في Runtime | VERIFIED | — |
| A03 | Inventory يجمع الحقائق دون قرار eligibility | Inventory prompt/tools | local tests + فصل القرار في Refund | VERIFIED | — |
| A04 | Refund يعيد Agent بأداتي context/initiate_refund | `build_refund_agent` | official task2؛ طلب إرجاع فعلي | VERIFIED | — |
| A05 | Standard 30 / Premium 60 مع الحدود | `refund_eligibility` | اختبارات حدود deterministic؛ Premium return فعلي | VERIFIED | Standard boundary مثبت محليًا؛ لا حاجة لإرجاع مدفوع إضافي |
| A06 | قراءة Inventory قبل Refund وتحديث الطلب بصورة مشروطة | `get_inventory_context`, `initiate_refund` | Runtime route، قراءة order status؛ `final-negative-verification.json` | VERIFIED | لا تحويل أموال؛ العملية تبدأ إرجاعًا فقط |
| A07 | Communication يعيد Agent وأداة full context | `build_communication_agent` | task2؛ final response يطابق communication_agent في DynamoDB | VERIFIED | — |
| A08 | WORKER_MODEL_ID؛ temperatures 0.1/0.1/0.3 | `_model`, worker builders | local config tests؛ official task2 | VERIFIED | — |
| A09 | ثلاث Retriever subagents مستقلة وأداة واحدة لكل منها | `build_policy_agent` | AST/config tests؛ policy Runtime trace | VERIFIED | — |
| A10 | IDs الصحيحة وأداة retrieve_from_knowledge_base | retriever tools, `_passages` | direct retrieval وofficial task5؛ `live-retrieval.json` | VERIFIED | — |
| A11 | ThreadPoolExecutor(max_workers=3) وas_completed | `search_all_policies` | AST؛ barrier test؛ actual policy trace | VERIFIED | — |
| A12 | نتائج غير فارغة من المجالات الثلاثة | `search_all_policies` | official task5 + Runtime cited policy findings | VERIFIED | — |
| A13 | Retriever T=0.0؛ coordinator T=0.2 | `_agent`, Policy builder | local configuration tests | VERIFIED | — |
| A14 | Orchestrator: Haiku config.ORCHESTRATOR_MODEL_ID؛ T=0.0 | `build_orchestrator_agent` | official task2؛ actual routing | VERIFIED | — |
| A15 | initialize_session أول أداة لكل turn | `initialize_session`, route fences | local tests؛ CloudWatch ترتيب الأدوات | VERIFIED | الطلب المحظور قد يتوقف قبل التهيئة بلا كتابة |
| A16 | order/status/return/refund: Inventory ثم Refund | `_required_workers`, `route` | local route cases؛ Runtime return trace | VERIFIED | status path مثبت محليًا |
| A17 | policy meanings إلى Policy | `_required_workers`, orchestrator prompt | Runtime premium-policy request | VERIFIED | — |
| A18 | account tier إلى Inventory دون Policy | `_required_workers` | deterministic account-route tests | VERIFIED | تحقق محلي؛ لم يُضَف استدعاء مدفوع غير لازم |
| A19 | arithmetic مباشرة إلى Communication | routing fences | Runtime math؛ $134.96؛ لا worker fields أخرى | VERIFIED | — |
| A20 | Communication آخر أداة ومؤلف الرد | `route`, `process_request` | state equality + tools trace + local rewrite rejection | VERIFIED | — |
| A21 | read-before-write؛ expected_version؛ worker fields مستقلة | `_create/_read/_update_workflow_state` | `live-state-verification.json`؛ concurrent writes version 2؛ رفض stale overwrite | VERIFIED | — |
| A22 | official task2 | untouched `tests/test_agent.py` | 40/40 ضمن التقييم الكامل | VERIFIED | — |
| B01 | content HIGH sexual/violence/hate؛ MEDIUM insults/misconduct | `create_guardrail` | official task3 يقرأ AWS configuration | VERIFIED | — |
| B02 | block card/SSN؛ anonymize email/phone | `create_guardrail` | official task3 + real SDK schema | VERIFIED | سياسة AWS متحققة؛ ليست تجربة جميع أمثلة PII |
| B03 | denied competitor/pricing/legal؛ profanity | `create_guardrail` | official task3؛ five live ApplyGuardrail probes | VERIFIED | — |
| B04 | STANDARD + us.guardrail.v1:0؛ السماح بالحساب | guardrail config + foundation role profile permission | AWS get_guardrail؛ math allowed؛ negotiation/legal/competitor blocked | VERIFIED | — |
| B05 | numbered version ورسائل منع ودية | `create_guardrail`, blocked path | AWS version 1 READY؛ actual runtime refusal | VERIFIED | — |
| B06 | CLI configure/deploy/deployed_runtime_arn | `deploy_to_agentcore_runtime`, supplied helper | `deploy-runtime-cli-credentials.log`؛ stack UPDATE_COMPLETE | VERIFIED | — |
| B07 | PUBLIC/HTTP ودور Foundation | runtime/CDK | `resume-cloud-audit.json`، live get_agent_runtime | VERIFIED | — |
| B08 | runtime env المطلوبة ومطابقة .env | deployment config | official task3 وAWS env-key audit | VERIFIED | .env خاص بمعرفات الموارد فقط |
| B09 | guardrail مرفق بكل agent وretriever | `_model`, `_apply_guardrail` | local attachment tests + actual runtime models | VERIFIED | — |
| B10 | runtime ARN حقيقي وtask3 ناجح | `.env`, CLI state | official all/task3؛ Runtime READY وinvocation ناجح | VERIFIED | — |
| C01 | create_memory + summaryMemoryStrategy | `configure_memory` | ACTIVE SUMMARIZATION؛ official task4 | VERIFIED | — |
| C02 | eventExpiryDuration=7؛ name/description؛ return ARN | `configure_memory` | AWS get_memory؛ official task4 15/15 | VERIFIED | — |
| C03 | تخزين أحداث وقراءة عبر turns مع عزل actor/session | `_memory_context`, `process_request` | Runtime تذكر turquoise؛ حدثان حقيقيان؛ `live-verification-summary.json` | VERIFIED | لا ندعي قياس زمن إنشاء كل long-term summary |
| C04 | 3 KBs self-managed وprefixes returns/shipping/warranty | `knowledge_bases.json`, deliver sync | ACTIVE + COMPLETE؛ `live-observability-summary.json` | VERIFIED | أنشئت عبر CFN وتظهر في Console |
| C05 | Titan v2، S3 Vectors الأصلي والفهارس الثلاثة | KB template + Foundation | AWS metadata، official task5 | VERIFIED | — |
| C06 | KB IDs صحيحة ومصادر متزامنة؛ retrieval فعلي | `.env`, `_passages` | official task5؛ S3 source passages؛ live RAG | VERIFIED | — |
| D01 | loggingConfiguration داخل try/except | `configure_observability` | local config/failure propagation tests + source | VERIFIED | — |
| D02 | CloudWatch INFO، log group، enabled | observability helper + runtime env | official task6؛ 82 actual INFO events | VERIFIED | — |
| D03 | X-Ray sampling=1.0 وTransaction Search 100% | configure_observability + helper | AWS ACTIVE destination + official task6 | VERIFIED | — |
| D04 | traces متصلة تشمل Policy وKB nodes | preserved tracer | BatchGetTraces للسيناريوهات؛ actual Service Graph | VERIFIED | — |
| D05 | أخطاء وزمن traces | `collect_evidence.py` | 4 traces إيجابية بلا error/fault؛ السيناريوهات 43.646/35.622/15.242 ثانية؛ regression 35.236 ثانية | VERIFIED | خطأ الصلاحية الأول موثق ومُصلح؛ رفض cross-customer يظهر SDK 500 متوقعًا |
| D06 | لقطة Service Map كاملة | `evidence/screenshots/xray-service-map.png` | الصورة الحالية أصلية لكنها مقصوصة؛ `screenshot-review.json` | BLOCKED | حفظ لقطة كاملة بكل العقد والمنطقة والنطاق الزمني |
| E01 | docstrings، builders تعيد Agent واحدًا، snake_case | primary source | official task2 + local review/config tests | VERIFIED | — |
| E02 | نماذج من config دون hardcoding في builders | `_model`, config | official task2 | VERIFIED | — |
| E03 | error recovery، ownership، idempotency | state/route/tool fences | 43 local tests؛ real refusal/isolation/idempotency probes | VERIFIED | SDK يعيد 500 عامًا عند forbidden session؛ لا يتسرب محتوى العميل |
| F01 | python tests/test_agent.py all | original official suite | `official-all.log`: 120/120؛ original SHA256 matches | VERIFIED | — |
| F02 | لقطة الاختبارات الناجحة 120 | `evidence/screenshots/official-tests-120.png` | لم يُحفظ الملف بعد | BLOCKED | لقطة حقيقية لعرض official-all.log في الطرفية |
| F03 | الكود والبنية والتبعيات و.env دون credentials | source + package script | allowlist، secret-key scan، ZIP manifest/checksums | VERIFIED | حزمة DRAFT مفحوصة؛ الصور تمنع FINAL |
| F04 | حزمة نهائية مكتملة الأدلة | `scripts/package_submission.py` | DRAFT مع manifest؛ final gate يرفض الصور غير المكتملة | BLOCKED | الصورتان فقط |
| X01 | Gateway/Lambda، frontend، dashboards إضافية | optional scaffolding | official rubric يصنف الإضافات اختيارية | NOT COMPLETED | ليست شروط نجاح؛ لم تُنشأ بنية غير لازمة |

الأدلة العامة في `starter/evidence/`. الردود الكاملة وARNs وsnapshots التفصيلية خاصة في `starter/.deployment/` ولا تدخل الأرشيف. صورة التصميم لا تحل محل صورة تشغيل. لا استنتاج بأن كل تشغيل قديم خالٍ من الأخطاء؛ أُصلح AccessDenied فعلي للحماية قبل نجاح جولة Runtime.

تحديث لقطة X-Ray: في 2026-10-22 10:42 UTC تحقق استدعاء سياسات واحد على Runtime v3 READY. Trace `1-6ad9e84e-16b9139a3d037de2a923ef42` مفهرسة وخريطتها متصلة بـPolicyAgent وCommunicationAgent وKnowledgeBase:returns/shipping/warranty، دون error/fault/throttle. الأدلة في `starter/evidence/trace-refresh-observability.json`. حالة D06 تبقى BLOCKED حتى حفظ ومراجعة لقطة Console الكاملة؛ لم تُعد الاختبارات الرسمية أو النشر.
