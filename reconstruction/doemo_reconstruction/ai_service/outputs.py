"""Reject incomplete or malformed adapter output before marking inference successful.

These checks establish the response contract, never architectural accuracy.
Empty OCR/detection lists are legitimate. Qwen must classify every supplied zone,
using unknown/uncertain when it cannot interpret one.
"""
import math


def validate_output(name, output, *, version, regions, width, height):
    def require(condition):
        if not condition:
            raise ValueError('Invalid engine output')

    def number(value, low, high):
        return type(value) in (int, float) and math.isfinite(value) and low <= value <= high

    def point(value):
        return (isinstance(value, list) and len(value) == 2
                and number(value[0], 0, width) and number(value[1], 0, height))

    require(isinstance(output, dict))
    require(output.get('engine') == name and output.get('model_version') == version)
    require(number(output.get('duration_seconds'), 0, 900))
    if name == 'qwen':
        zones = output.get('zones')
        require(isinstance(zones, list) and len(zones) == len(regions))
        expected = {r['id'] for r in regions}
        seen = set()
        for zone in zones:
            require(isinstance(zone, dict) and set(zone) == {'id', 'label', 'uncertain', 'note', 'status'})
            require(isinstance(zone['id'], str) and zone['id'] in expected and zone['id'] not in seen)
            seen.add(zone['id'])
            require(zone['label'] in ('building', 'room', 'stairs', 'circulation', 'annotation', 'unknown'))
            require(type(zone['uncertain']) is bool and zone['status'] == 'pending')
            require(zone['label'] != 'unknown' or zone['uncertain'])
            require(isinstance(zone['note'], str) and len(zone['note']) <= 1000)
        require(seen == expected)
    elif name == 'paddleocr':
        texts = output.get('texts')
        require(isinstance(texts, list) and len(texts) <= 20000)
        require(output.get('coordinate_space') == 'input_image_pixels')
        for text in texts:
            require(isinstance(text, dict))
            polygon = text.get('polygon')
            require(isinstance(polygon, list) and 3 <= len(polygon) <= 1000)
            require(all(point(p) for p in polygon))
            require(isinstance(text.get('text'), str) and len(text['text']) <= 20000)
            require(number(text.get('confidence'), 0, 1) and text.get('status') == 'pending')
    elif name == 'rtmdet':
        detections = output.get('detections')
        require(isinstance(detections, list) and len(detections) <= 500)
        require(output.get('architectural_wall_detector') is False and output.get('usage') == 'diagnostic_only')
        for detection in detections:
            require(isinstance(detection, dict))
            box = detection.get('bbox')
            require(isinstance(box, list) and len(box) == 4 and point(box[:2]) and point(box[2:]))
            require(box[0] < box[2] and box[1] < box[3])
            require(isinstance(detection.get('label'), str) and len(detection['label']) <= 200)
            require(number(detection.get('confidence'), 0, 1) and detection.get('status') == 'pending')
    else:
        raise ValueError('Unknown engine')
    return output
