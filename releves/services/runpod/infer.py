"""Engine adapters, executed only by the corresponding existing Python environment.

No installation, downloads, training or arbitrary shell commands. The adapters need
an actual RunPod acceptance test against the installed package versions.
"""
import json
import os
import sys
from pathlib import Path
engine,source,output=sys.argv[1:4]
context_file=sys.argv[4] if len(sys.argv)==5 else None
if len(sys.argv) not in (4,5) or (context_file and engine!='qwen'):raise ValueError('Arguments invalides')
if engine=='paddleocr':
    from paddleocr import PaddleOCR
    detection=os.environ.get('DOEMO_PADDLE_DETECTION_MODEL')
    recognition=os.environ.get('DOEMO_PADDLE_RECOGNITION_MODEL')
    if not detection or not recognition or not Path(detection).is_dir() or not Path(recognition).is_dir():
        raise ValueError('Renseigner les deux répertoires de modèles PaddleOCR déjà installés')
    pipeline=PaddleOCR(lang=os.environ.get('DOEMO_OCR_LANG','fr'),text_detection_model_dir=detection,
                      text_recognition_model_dir=recognition,use_doc_orientation_classify=False,
                      use_doc_unwarping=False,use_textline_orientation=False)
    predictions=list(pipeline.predict(source))
    if len(predictions)!=1:raise ValueError('Une image attendue')
    result=predictions[0].json
    if isinstance(result,str):result=json.loads(result)
elif engine=='qwen':
    import torch
    from transformers import AutoProcessor,AutoModelForImageTextToText
    path=os.environ.get('DOEMO_QWEN_MODEL','/workspace/doemo-studio/models/qwen/Qwen3.5-9B')
    processor=AutoProcessor.from_pretrained(path,local_files_only=True)
    model=AutoModelForImageTextToText.from_pretrained(path,local_files_only=True,torch_dtype='auto',device_map='auto')
    from qwen_prompt import parse,prompt
    reference=parse(Path(context_file).read_text()) if context_file else None
    from PIL import Image
    messages=[{'role':'user','content':[{'type':'image','image':Image.open(source).convert('RGB')},{'type':'text','text':prompt(reference)}]}]
    inputs=processor.apply_chat_template(messages,tokenize=True,add_generation_prompt=True,return_dict=True,return_tensors='pt').to(model.device)
    with torch.inference_mode():tokens=model.generate(**inputs,max_new_tokens=2048,do_sample=False)
    text=processor.batch_decode(tokens[:,inputs['input_ids'].shape[1]:],skip_special_tokens=True)[0]
    result=json.loads(text)  # Fail closed on malformed / fenced JSON, no fabricated repair.
elif engine=='rtmdet':
    from mmdet.apis import DetInferencer
    config=os.environ.get('DOEMO_RTMDET_CONFIG');weights=os.environ.get('DOEMO_RTMDET_WEIGHTS')
    if not config or not weights or not Path(config).is_file() or not Path(weights).is_file():
        raise ValueError('Configuration et poids locaux RTMDet requis')
    inference=DetInferencer(model=config,weights=weights,device='cuda:0')
    result=inference(source,return_datasamples=False,no_save_vis=True,no_save_pred=True)['predictions'][0]
else:raise ValueError('Moteur inconnu')
# FUSE is not used for intermediates; the gateway result lives in /tmp.
Path(output).write_text(json.dumps(result,ensure_ascii=False))
