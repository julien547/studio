"""CPU-only validation for the PaddleOCR recognition training adapter.

Supported factory API: PaddleOCR v3.3.0 ppocr, CTCHead or CTC MultiHead,
SimpleDataSet, local pretrained .pdparams. Detection/distillation are refused.
No framework imports, downloads or GPU operations occur in this module.
"""
import copy
import hashlib
import json
from collections import Counter
from pathlib import Path
from training_data import ocr_splits
from artifacts import sha256


def source_hash(repository):
    repository=Path(repository).resolve();files=[]
    for package in ('ppocr','tools'):
        for path in sorted((repository/package).rglob('*.py')):
            if path.is_symlink() or not path.resolve().is_relative_to(repository):raise ValueError('Lien de code externe refusé')
            files.append((str(path.relative_to(repository)),sha256(path)))
    if not files or not (repository/'ppocr/modeling/architectures/__init__.py').is_file():raise ValueError('Dépôt source PaddleOCR complet requis')
    return hashlib.sha256(json.dumps(files,separators=(',',':')).encode()).hexdigest()


def validate_labels(directory,dictionary,use_space,max_length):
    splits=ocr_splits(directory)
    characters=Path(dictionary).read_text(encoding='utf-8').splitlines()
    if not characters or any(len(c)!=1 for c in characters) or len(set(characters))!=len(characters):raise ValueError('Dictionnaire de caractères unique, un caractère par ligne requis')
    if use_space:
        if ' ' in characters:raise ValueError('Espace dupliqué dans le dictionnaire')
        characters.append(' ')
    allowed=set(characters);rows=[json.loads(line) for line in (Path(directory)/'ocr.jsonl').read_text().splitlines()]
    groups={};images=set()
    for row in rows:
        if row.get('split') not in ('train','validation','test'):raise ValueError('Lot OCR inconnu')
        text=row['text'];path=(Path(directory)/row['image']).resolve()
        if row['image'] in images:raise ValueError('Image OCR dupliquée')
        images.add(row['image'])
        if len(text)>max_length or any(c not in allowed for c in text):raise ValueError('Transcription trop longue ou caractère absent du dictionnaire : aucune suppression silencieuse autorisée')
        fingerprint=sha256(path)
        if fingerprint in groups and groups[fingerprint]!=row['split']:raise ValueError('Même image OCR dans plusieurs lots')
        groups[fingerprint]=row['split']
        from PIL import Image
        with Image.open(path) as im:
            if im.format!='PNG' or im.width*im.height>40_000_000:raise ValueError('Image OCR incompatible')
            im.verify()
    return splits,rows


def configuration(original,dataset,work,dictionary,epochs,batch_size,rate):
    cfg=copy.deepcopy(original)
    arch=cfg.get('Architecture',{});post=cfg.get('PostProcess',{});head=arch.get('Head',{})
    if arch.get('model_type')!='rec' or arch.get('algorithm') not in ('CRNN','SVTR','SVTR_LCNet') or head.get('name') not in ('CTCHead','MultiHead') or post.get('name')!='CTCLabelDecode':raise ValueError('Profil de reconnaissance CTC compatible requis ; détection, distillation et formules refusées')
    if (head['name']=='CTCHead' and cfg.get('Loss',{}).get('name')!='CTCLoss') or (head['name']=='MultiHead' and cfg.get('Loss',{}).get('name')!='MultiLoss'):raise ValueError('Perte incompatible avec la tête de reconnaissance')
    def local_only(value):
        if isinstance(value,dict):
            for child in value.values():local_only(child)
        elif isinstance(value,list):
            for child in value:local_only(child)
        elif isinstance(value,str) and '://' in value:raise ValueError('Téléchargement interdit dans le profil')
    local_only(cfg)
    if arch.get('Backbone',{}).get('pretrained'):raise ValueError('Initialisation distante du backbone refusée ; utiliser les poids locaux explicites')
    global_cfg=cfg.setdefault('Global',{})
    max_length=global_cfg.get('max_text_length');use_space=global_cfg.get('use_space_char',False)
    if type(max_length) is not int or not 1<=max_length<=400 or type(use_space) is not bool:raise ValueError('Longueur et dictionnaire explicites requis')
    splits,rows=validate_labels(dataset,dictionary,use_space,max_length)
    global_cfg.update(use_gpu=True,distributed=False,use_amp=False,to_static=False,character_dict_path=str(dictionary),save_model_dir=str(work),
                      epoch_num=epochs,pretrained_model=None,checkpoints=None,lower=False)
    for field,split in (('Train','train'),('Eval','validation')):
        section=cfg.get(field,{})
        if section.get('dataset',{}).get('name')!='SimpleDataSet' or not section['dataset'].get('transforms'):raise ValueError('SimpleDataSet et transformations explicites requis')
        section['dataset'].update(data_dir=str(dataset),label_file_list=[splits[split]],ratio_list=[1.0])
        # No opaque multi-scale/reset sampler or multiprocessing state to resume.
        section.pop('sampler',None)
        section['loader']={'shuffle':field=='Train','drop_last':False,'batch_size_per_card':batch_size if field=='Train' else 1,'num_workers':0,'use_shared_memory':False}
    cfg['Optimizer']={'name':'Adam','lr':{'learning_rate':rate}} # Deliberately fixed, no inherited schedule/AMP.
    return cfg,splits,rows


class CheckedLoader:
    """Reject missing/replaced/case-folded labels, including in shuffled training."""
    def __init__(self,loader,expected,decode):self.loader=loader;self.expected=Counter(expected);self.decode=decode
    def __len__(self):return len(self.loader)
    def __iter__(self):
        remaining=self.expected.copy()
        for batch in self.loader:
            for label in self.decode(batch):
                if remaining[label]<=0:raise ValueError('Le lecteur a modifié ou remplacé une transcription')
                remaining[label]-=1
            yield batch
        if any(remaining.values()):raise ValueError('Transcriptions omises par le lecteur')


class ExactMetric:
    def __init__(self,expected):self.expected=list(expected);self.pairs=[]
    def add(self,decoded):
        predictions,labels=decoded
        if len(predictions)!=len(labels):raise ValueError('Sortie OCR désalignée')
        for pred,label in zip(predictions,labels):
            index=len(self.pairs)
            if index>=len(self.expected) or label[0]!=self.expected[index]:raise ValueError('Transcription modifiée, omise ou réordonnée par le lecteur OCR')
            if not isinstance(pred[0],str):raise ValueError('Prédiction OCR invalide')
            self.pairs.append((label[0],pred[0]))
    def finish(self):
        if len(self.pairs)!=len(self.expected):raise ValueError('Évaluation OCR incomplète')
        from training_data import ocr_metrics
        values=ocr_metrics(self.pairs)
        return {'cer':values['cer'],'wer':values['wer'],'samples':values['samples'],
                'exact_match':sum(a==b for a,b in self.pairs)/len(self.pairs)}
