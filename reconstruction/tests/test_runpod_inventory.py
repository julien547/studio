"""Synthetic host fixtures: these tests do not attest to the real RunPod state."""
import copy
import importlib.util
from pathlib import Path
import threading

import pytest
from doemo_reconstruction.ai_service.service import RemoteWorker

spec=importlib.util.spec_from_file_location('runpod_inventory',Path(__file__).parents[1]/'runpod/inventory.py')
inventory=importlib.util.module_from_spec(spec);spec.loader.exec_module(inventory)


def report():
    return {'identity':{'runpod_pod_id':'current-pod'},
            'gpu':{'query_ok':True,'devices':['NVIDIA RTX A6000, 46068 MiB, driver']},
            'storage':{'mount':'/workspace fuse.geesefs',
                       'backups':{'present':True,'entry_count':7},
                       'models':{'present':True,'entry_count':3}}}


def test_missing_environment_and_broken_python_are_distinct(tmp_path):
    folder=tmp_path/'venv'
    assert inventory.interpreter_state(folder)['state']=='environment_missing'
    (folder/'bin').mkdir(parents=True)
    (folder/'bin/python').symlink_to('/missing-python-fixture/bin/python3')
    state=inventory.interpreter_state(folder)
    assert state['state']=='interpreter_target_missing'
    assert state['directory_present'] and state['python_entry_present']
    assert not state['inference_verified']


def test_present_interpreter_is_not_proof_of_model_inference(tmp_path):
    folder=tmp_path/'venv';(folder/'bin').mkdir(parents=True)
    python=folder/'bin/python';python.write_text('#!/bin/sh\nexit 0\n');python.chmod(0o700)
    state=inventory.interpreter_state(folder)
    assert state['state']=='present_requires_functional_test' and not state['inference_verified']


def test_restore_preflight_requires_gpu_pod_and_persistent_layout():
    inventory.require_restore_host(report())
    for field,value in [('identity',{'runpod_pod_id':None}),('gpu',{'query_ok':False})]:
        data=report();data[field]=value
        with pytest.raises(ValueError):inventory.require_restore_host(data)
    for field,value in [('mount','/ overlay'),('backups',{'present':False}),('models',{'present':True,'entry_count':0})]:
        data=report();data['storage'][field]=value
        with pytest.raises(ValueError):inventory.require_restore_host(data)


def test_readiness_rejects_old_pod_after_migration():
    remote=RemoteWorker(b'not-used')
    remote.health=lambda pod:{'ready':True,'pod_id':'old-pod','draining':False}
    with pytest.raises(RuntimeError,match='Pod actif'):
        remote.wait_ready({'id':'new-pod'},threading.Event(),timeout=1)
    remote.health=lambda pod:{'ready':True,'pod_id':'new-pod','draining':False}
    remote.wait_ready({'id':'new-pod'},threading.Event(),timeout=1)
