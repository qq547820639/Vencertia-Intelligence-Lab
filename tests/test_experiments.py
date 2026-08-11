from vencertia.domain import Belief, Experiment
from vencertia.experiments import ExperimentOptimizer

def test_critical_belief_is_prioritized():
    beliefs=[Belief(id='wtp',statement='pay'),Belief(id='problem',statement='pain')]
    exps=[
        Experiment(id='a',name='A',target_belief_ids=['problem'],expected_information_gain=.9,decision_impact=.9,cost=1,days=1,reversibility=1,description='x',success_signal='x',failure_signal='x'),
        Experiment(id='b',name='B',target_belief_ids=['wtp'],expected_information_gain=.7,decision_impact=.8,cost=1,days=1,reversibility=1,description='x',success_signal='x',failure_signal='x'),
    ]
    ranked=ExperimentOptimizer().rank(exps,beliefs,critical_belief_id='wtp')
    assert ranked[0].experiment.id=='b'
