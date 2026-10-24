# تشغيل NovaMart والتسليم

AWS منشور في `us-east-1` باستخدام `novamart-dev`. Runtime: READY؛ Memory: ACTIVE مع SUMMARIZATION و7 أيام؛ ثلاث KBs: ACTIVE ومتزامنة على S3 Vectors؛ Guardrail version 1 READY. التقييم الرسمي الكامل 120/120، والاختبارات المحلية 43 ناجحة. راجع `REQUIREMENT_STATUS.md` للمتبقي والصور؛ لا تُعد نشر البنية أو seeding عند الاستئناف.

من جذر المشروع:

```bash
cd starter
export AWS_PROFILE=novamart-dev
export AWS_REGION=us-east-1
export AWS_DEFAULT_REGION=us-east-1
export AWS_MAX_ATTEMPTS=1
export PATH="$PWD/.tools/agentcore/node_modules/.bin:$PWD/.venv312/bin:$PATH"
export UV_CACHE_DIR="$PWD/.tools/uv-cache"
export UV_PYTHON_INSTALL_DIR="$PWD/.tools/python"
aws sts get-caller-identity --profile novamart-dev --region us-east-1
```

عند ExpiredToken، حدّث اعتمادات Udacity المؤقتة محليًا في profile نفسه. لا تُرسل المفاتيح أو tokens. لا تستخدم SSO login إلا إذا كان profile مهيأً لـSSO. بيئة Python 3.12.14 وCLI 0.30.0 مثبتة محليًا؛ `bash scripts/setup.sh` مخصص لجهاز جديد أو بيئة مفقودة، وليس خطوة استئناف لازمة.

عرض الأدلة الموجودة لا يستدعي النماذج:

```bash
cat evidence/official-all.log
cat evidence/final-live-verification.log
cat evidence/live-verification-summary.json
cat evidence/live-observability-summary.json
```

فحص محلي دون inference مدفوع:

```bash
bash scripts/validate.sh
```

الاختبار الرسمي الحقيقي (يشمل استدلال RAG محدودًا):

```bash
python tests/test_agent.py all
```

التحقق الإضافي المكتمل شمل خمسة safety probes، ثلاثة Runtime scenarios، ودورين لاختبار الذاكرة، ثم رفض طلب محظور وعزل العميل وidempotency. أوامره القابلة للإعادة عند وجود سبب للتحقق:

```bash
python scripts/verify_live.py
python scripts/verify_negative.py
python scripts/collect_evidence.py
```

لا تعِد الجولة المدفوعة لمجرد التقاط صورة؛ اعرض سجل نجاحها الموجود. `verify_live.py` يبدأ إرجاع الطلب التجريبي المحدد إذا لم يبدأ سابقًا. يتوقف عند أي فشل ولا يخفي partial evidence. محفوظاته التفصيلية في `.deployment/` خاصة.

لاستدعاء يدوي واحد:

```bash
python src/agent_orchestrator.py invoke "What is the return policy for premium customers?" CUST-002
agentcore status
```

واجهة CLI مصادق عليها بـIAM. customer_id يختاره مشغّل المختبر؛ frontend متعدد العملاء يحتاج ربط الهوية بمصادقة خاصة به، وهو خارج Rubric الأساسي. الجلسات معزولة، والطلبات المتعارضة تُرفض. رفض ملكية الجلسة يُترجم حاليًا من SDK إلى HTTP 500 عام دون عرض بيانات العميل. لا ندعي أن كل خطأ في السجلات مشكلة غير معالجة؛ راجع أوقات probes السلبية.

سياسة الإرجاع تستخدم delivered_at إذا توفر، وإلا order_date كـfallback موضح، ولا تعتبر estimated_delivery تاريخ تسليم فعليًا. initiate_refund يبدأ طلب إرجاع ولا يحوّل أموالًا. طلب بلا reason قد يتلقى سؤال متابعة. الاستفسار العام عن Premium لا يثبت أن العميل Premium.

النشر يستخدم AgentCore CLI → CDK → CloudFormation مع CliCredentialsStackSynthesizer: جلسة المستخدم المؤقتة تنفذ عمليات النشر المصرح بها، وRuntime يعمل بدور Foundation المحدود. لا AdministratorAccess جديد. إعداد PUBLIC يعني اتصال الخدمة، والاستدعاء يبقى مصادقًا بـAWS IAM.

عند تعديل حقيقي يحتاج نشرًا، استخدم المسار الموجود فقط:

```bash
python scripts/deliver.py runtime --apply
```

لا تشغّل foundation أو all --apply على البنية العاملة دون الحاجة، لأن seeding يعيد أوضاع بيانات الاختبار. أسماء الموارد وARNs والقيم الحقيقية محفوظة في `.env` و`.deployment/resources.json` محليًا. القوالب والإعدادات القابلة للمراجعة في `infrastructure/` و`agentcore/`.

## صور التسليم

1. في AWS Console افتح CloudWatch → X-Ray traces → Service map في us-east-1 واختر الفترة التي تشمل الاختبار. احفظ كامل الرسم مع جميع العقد، خصوصًا PolicyAgent وKnowledgeBase للسياسات الثلاث، والنطاق الزمني والمنطقة، إلى `evidence/screenshots/xray-service-map.png`. النسخة الحالية المقصوصة تحتاج استبدالًا.
2. افتح الطرفية واعرض `cat evidence/official-all.log`؛ احفظ لقطة حقيقية تظهر نجاح الاختبارات و120/120 في `evidence/screenshots/official-tests-120.png`.
3. تُراجع الصور بصريًا ويُحدث `evidence/screenshot-review.json` مع SHA256؛ وجود PNG وحده لا يثبت اكتمال الدليل. لا تُولّد صورة تحاكي الطرفية أو Console.

الحزمة المحلية الخاصة (تشمل .env بمعرفات موارد فقط، دون credentials):

```bash
python scripts/package_submission.py
python scripts/package_submission.py --final
```

الأمر الأول ينتج `../submission/NovaMart-draft.zip` مع قائمة النواقص. الأمر الثاني يرفض التسليم إن نقصت جولة Runtime أو 120/120 أو مراجعة الصور؛ عند نجاحه ينتج `../submission/NovaMart-final.zip`. هذه بنية حزمة محلية منظمة؛ نص المشروع لا يحدد تنسيق بوابة الرفع. لا تنشر الحزمة أو .env أو .deployment للعامة. لا تُضمّن البيئات والكاش وبيانات AWS.

## الميزانية والتنظيف

الموافقة الحالية تقدير $3–$8، والتوقف للمراجعة عند تقدير $10، والميزانية الكلية $25. Billing يتأخر؛ Cost Explorer لا يساوي رصيد Udacity. راجع `EXPENSE_LOG.md`. لم يُضف OpenSearch أو provisioned throughput أو Gateway/Lambda اختياري.

التنظيف بعد حفظ الأدلة والتسليم وبقرار المستخدم فقط:

```bash
python infrastructure/cleanup.py
python infrastructure/cleanup.py --yes
```

الأول dry-run. يتحقق من المعرفات المسجلة وملكية المشروع؛ يحتفظ بـCDKToolkit وTransaction Search المشتركين. لا تنظيف تلقائي ولا حذف موارد غير تابعة للمشروع. بعد انتهاء الجلسات قد تبقى رسوم التخزين والذاكرة والسجلات حتى التنظيف.
