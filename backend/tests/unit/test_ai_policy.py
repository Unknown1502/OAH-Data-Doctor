"""The LLM layer can only rephrase: ungrounded numbers are rejected and the product works without it."""

from datadoctor.ai.explainer import MockExplainer, TemplateExplainer, get_explainer, numbers_are_grounded
from datadoctor.rules.registry import run_rule
from tests.helpers import KN, dataset, stats_obs


def _anchor_finding():
    ds = dataset(stats_obs("A", average=198000, maximum=211000, minimum=185000, std_dev=18385, median=19.8))
    return run_rule("SEM-STAT-001", ds, KN)[0]


def test_template_explanation_is_deterministic_and_complete():
    f = _anchor_finding()
    a, b = TemplateExplainer().explain(f), TemplateExplainer().explain(f)
    assert a == b and a.method == "template"
    assert "19.8" in a.text and "data owner" in a.text


def test_grounded_llm_text_is_accepted():
    f = _anchor_finding()
    out = MockExplainer("The median of 19.8 sits far below the minimum of 185,000, so these statistics cannot all be right.").explain(f)
    assert out.method == "mock"


def test_llm_text_with_invented_numbers_falls_back_to_template():
    f = _anchor_finding()
    assert not numbers_are_grounded("The true temperature was probably 19.8 C, about 42% lower.", f)
    out = MockExplainer("The true value is probably 21.3 C.").explain(f)
    assert out.method == "template" and out.fallback_reason


def test_no_provider_means_template():
    assert isinstance(get_explainer(None), TemplateExplainer)
