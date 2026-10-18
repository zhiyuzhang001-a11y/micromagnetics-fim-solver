"""Discover constructor fields without constructing models or evaluating fields."""
import dataclasses
import inspect
from . import model, initial, simulation, stages


def parameters():
    result = {}
    for module in (model, initial, simulation, stages):
        for name, cls in vars(module).items():
            if not inspect.isclass(cls) or cls.__module__ != module.__name__ or not dataclasses.is_dataclass(cls):
                continue
            result[name] = {'signature': str(inspect.signature(cls)),
                            'fields': {f.name: {'type': str(f.type),
                                               'required': f.default is dataclasses.MISSING and f.default_factory is dataclasses.MISSING,
                                               'default': repr(f.default) if f.default is not dataclasses.MISSING else None}
                                       for f in dataclasses.fields(cls)}}
    result['Grid']['fields']['cells'].update(required=False, default='None', constraint='exactly one of size/cells')
    result['Grid']['fields']['size'] = {'type':'tuple[float,float,float] | None', 'required':False, 'default':'None', 'unit':'m', 'constraint':'exactly one of size/cells; single layer'}
    return {'units': 'SI except B_ext [T]', 'constructors': result,
            'reference': 'docs/interface-v01/PARAMETERS.md',
            'defaults': 'zero external field; no current; no energy terms unless listed; no implicit initial state'}
