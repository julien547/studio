import io
import json
import sys
import zipfile
from pathlib import Path
from types import SimpleNamespace
import pytest
from PIL import Image

@pytest.fixture
def modules(monkeypatch):
 monkeypatch.syspath_prepend(str(Path(__file__).parents[2]/'services/runpod'))
 import artifacts,training_data,rtmdet_pipeline
 return artifacts,training_data,rtmdet_pipeline


def test_persisted_artifacts_are_immutable_verified_and_partial_copies_not_registered(tmp_path,modules):
 artifacts,_,_=modules
 weights=tmp_path/'weights.pth';weights.write_bytes(b'fixture, not real trained weights')
 first=artifacts.preserve({'weights.pth':weights},tmp_path/'volume',{'engine':'rtmdet'})
 assert artifacts.verify(first)['metadata']['engine']=='rtmdet'
 second=artifacts.preserve({'weights.pth':weights},tmp_path/'volume',{'engine':'rtmdet'})
 assert first!=second and first.exists()
 (second.parent/'weights.pth').write_bytes(b'corrupted')
 with pytest.raises(ValueError):artifacts.verify(second)
 with pytest.raises(ValueError):artifacts.preserve({'../escape':weights},tmp_path/'volume',{})
 assert not (tmp_path/'escape').exists()


def fixture(root):
 root.mkdir();(root/'images').mkdir();images=[];annotations=[]
 for n,split in enumerate(('train','validation','test'),1):
  name=f'images/{n}.png';Image.new('RGB',(100,100)).save(root/name)
  images.append({'id':n,'file_name':name,'width':100,'height':100,'split':split,'document_sha256':str(n)})
  annotations.append({'id':n,'image_id':n,'category_id':1,'bbox':[1,2,3,4],'area':12,'iscrowd':0})
 value={'images':images,'annotations':annotations,'categories':[{'id':1,'name':'Extincteur portatif'}]}
 (root/'coco.json').write_text(json.dumps(value))
 (root/'ocr.jsonl').write_text('\n'.join(json.dumps({'image':im['file_name'],'text':'H₂O','split':im['split']}) for im in images))
 return value


def test_dataset_conversion_keeps_splits_and_exact_ocr_characters(tmp_path,modules):
 _,data,_=modules;root=tmp_path/'data';value=fixture(root)
 splits,classes=data.detection_splits(root)
 assert set(splits)=={'train','validation','test'} and classes==['Extincteur portatif']
 assert len(json.loads(Path(splits['test']).read_text())['images'])==1
 ocr=data.ocr_splits(root)
 assert Path(ocr['train']).read_text()=='images/1.png\tH₂O\n'
 assert data.ocr_metrics([('H₂O','H2O')])['cer']==pytest.approx(1/3)
 assert data.ocr_metrics([('PCF','PCF'),('CO₂','CO₂')])['cer']==0
 value['images'][1]['document_sha256']='1';(root/'coco.json').write_text(json.dumps(value))
 with pytest.raises(ValueError,match='plusieurs splits'):data.detection_splits(root)


def test_unpack_refuses_traversal_and_coco_rejects_wrong_frame(tmp_path,modules):
 _,data,_=modules;bundle=tmp_path/'bad.zip'
 with zipfile.ZipFile(bundle,'w') as z:z.writestr('../escape.png',b'bad')
 with pytest.raises(ValueError):data.unpack(bundle,tmp_path/'out')
 assert not (tmp_path/'escape.png').exists()
 root=tmp_path/'images';value=fixture(root);value['images'][0]['width']=120
 (root/'coco.json').write_text(json.dumps(value))
 with pytest.raises(ValueError,match='repère'):data.detection_splits(root)


def test_training_driver_requires_explicit_authorization_before_gpu_import(modules):
 _,_,driver=modules
 with pytest.raises(ValueError,match='Autorisation'):driver.run(SimpleNamespace(epochs=1,batch_size=1,learning_rate=.0001,authorize_gpu_training=False))
 with pytest.raises(ValueError):driver.validate_parameters(10000,1,.0001)
