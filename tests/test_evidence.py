from vencertia.domain import *
from vencertia.evidence import EvidenceEngine

def test_payment_moves_more_than_model_inference():
    b=[Belief(id='x',statement='will pay')]
    common=dict(belief_id='x',claim='x',verification=Verification.VERIFIED,direction=Direction.SUPPORTS,strength=1,source_reliability=1,directness=1)
    pay=Evidence(id='p',source_type=SourceType.REAL_PAYMENT,**common)
    model=Evidence(id='m',source_type=SourceType.MODEL_INFERENCE,**common)
    _,a=EvidenceEngine().apply(b,[pay,model])
    assert a[0].alpha_delta > a[1].alpha_delta

def test_correlated_evidence_diminishes():
    b=[Belief(id='x',statement='x')]
    es=[Evidence(id=str(i),belief_id='x',claim='same batch',source_type=SourceType.PRIMARY_RESEARCH,verification=Verification.VERIFIED,direction=Direction.SUPPORTS,strength=1,source_reliability=1,directness=1,independence_key='batch') for i in range(3)]
    _,a=EvidenceEngine().apply(b,es)
    assert a[0].effective_weight > a[1].effective_weight > a[2].effective_weight
