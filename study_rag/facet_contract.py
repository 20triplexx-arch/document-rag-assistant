"""Internal single-owner answer units; public answers remain unmodified v2."""
from copy import deepcopy
import re

from .citation_spans import GenerationShapeError, hydrate


class FacetContract:
    def __init__(self, plan, spans, facts):
        self.plan=plan;self.spans=spans;self.facts=facts
        self.faces={f['id']:f for f in plan.get('necessary_faces',[])}
        if not self.faces:raise GenerationShapeError('必要面契约为空。')
        self.used=set()
        self.groups={}
        for face_id,face in self.faces.items():
            relevant=[]
            for fact_id,fact in facts.items():
                if not any(ref.split(':')[0] in face.get('evidence_ids',[]) for ref in fact['references']):continue
                subject=fact.get('subject','')
                if subject.split('.')[-1] in {'print','strftime','now','utcnow','isoformat'} and not re.search(r'print|时间戳|日志|日期',plan['question'],re.I):continue
                if face.get('object') and face.get('dimension')=='source_relations':
                    target=face['object']
                    if fact.get('owner') not in {target,target.split('.')[-1]} and subject not in {target,target.split('.')[-1]}:continue
                if fact['kind']=='definition' and not re.search(r'定义|导入|归属|本地',plan['question']):continue
                relevant.append(fact_id)
            if face.get('dimension')=='source_relations' and relevant:
                # Minimal source-observed relations for this object; no repeated free rewrite.
                self.groups['G'+str(len(self.groups)+1)]={'face_id':face_id,'fact_ids':relevant[:8]}

    def unit(self, unit):
        if not isinstance(unit,dict):raise GenerationShapeError('内容单元必须是对象。')
        unit=dict(unit);face_id=unit.pop('face_id',None)
        if face_id not in self.faces or face_id in self.used:raise GenerationShapeError('未知或重复的必要面编号。')
        if unit.get('type')=='source_facts':raise GenerationShapeError('本轮必须选择必要面事实组。')
        face=self.faces[face_id]
        if unit.get('type')=='fact_group':
            if set(unit)!={'type','group_id'} or unit['group_id'] not in self.groups:raise GenerationShapeError('事实组编号无效。')
            group=self.groups[unit['group_id']]
            if group['face_id']!=face_id:raise GenerationShapeError('事实组与必要面不一致。')
            facts=[self.facts[i] for i in group['fact_ids']]
            unit={'text':' '.join(f['text'] for f in facts),'references':list(dict.fromkeys(r for f in facts for r in f['references']))}
        elif any(g['face_id']==face_id for g in self.groups.values()):
            raise GenerationShapeError('源码事实面只能选择服务端事实组。')
        rendered=hydrate(unit,self.spans,self.facts)
        def refs(node):
            if isinstance(node,dict):
                yield from node.get('references',[])
                for key,value in node.items():
                    if key!='references':yield from refs(value)
            elif isinstance(node,list):
                for value in node:yield from refs(value)
        if any(ref['evidence_id'] not in face.get('evidence_ids',[]) for ref in refs(rendered)):
            raise GenerationShapeError('引用不属于该必要面的来源。')
        if self.plan.get('object_status') in {'indexed','ambiguous'} and re.search(r'(?:课件|语料|资料).{0,10}(?:未收录|没有这个|不存在这个)',str(rendered)):
            raise GenerationShapeError('已收录对象不能声明为语料不存在。')
        self.used.add(face_id)
        return rendered

    def final(self, value):
        if not isinstance(value,dict) or set(value)!={'blocks','missing_face_ids'} or not isinstance(value['blocks'],list):
            raise GenerationShapeError('顶层必须是blocks与missing_face_ids。')
        blocks=[self.unit(unit) for unit in value['blocks']]
        gaps=value['missing_face_ids']
        if not isinstance(gaps,list) or any(not isinstance(i,str) or i not in self.faces for i in gaps) or len(gaps)!=len(set(gaps)) or self.used&set(gaps):
            raise GenerationShapeError('缺口编号无效或重复正文必要面。')
        if self.used|set(gaps)!=set(self.faces):raise GenerationShapeError('必要面被静默遗漏。')
        details=[]
        for i in gaps:
            face=self.faces[i];label=face.get('object') or face.get('dimension') or i
            prefix='对象已在语料中收录，但当前未取到' if self.plan.get('object_status')=='indexed' else '当前证据未能确定'
            details.append(prefix+f'「{label}」'+('（'+face['version']+'）' if face.get('version') else '')+'的完整依据。')
        return {'schema_version':2,'status':('partial' if blocks else 'insufficient') if gaps else 'answered',
                'blocks':blocks,'missing_information':' '.join(details)}

    def schema(self, base):
        schema=deepcopy(base)
        # Internal source_facts is replaced by indivisible, facet-bound fact groups.
        schema['$defs'].pop('SourceFacts',None)
        choices=[]
        items=base['properties']['blocks']['items']
        allowed={c.get('$ref') for c in items.get('oneOf',[items])}
        for name in ['Paragraph','ListBlock','TableBlock','CodeBlock']:
            if '#/$defs/'+name not in allowed:continue
            node=schema['$defs'][name]
            variants=node.get('oneOf',[node])
            for variant in variants:
                variant.setdefault('properties',{})['face_id']={'type':'string','enum':list(self.faces)}
                variant.setdefault('required',[]).append('face_id')
            choices.append({'$ref':'#/$defs/'+name})
        if self.groups:
            schema['$defs']['FactGroup']={'type':'object','additionalProperties':False,'required':['face_id','type','group_id'],
                'properties':{'face_id':{'type':'string','enum':list(self.faces)},'type':{'const':'fact_group'},
                              'group_id':{'type':'string','enum':list(self.groups)}}}
            choices.append({'$ref':'#/$defs/FactGroup'})
        schema['properties']={'blocks':{'type':'array','items':{'oneOf':choices},'maxItems':len(self.faces)},
            'missing_face_ids':{'type':'array','uniqueItems':True,'items':{'type':'string','enum':list(self.faces)}}}
        schema['required']=['blocks','missing_face_ids']
        return schema
