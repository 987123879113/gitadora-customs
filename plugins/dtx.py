# Docs:
# https://osdn.net/projects/dtxmania/wiki/DTX%20data%20format
# https://osdn.net/projects/dtxmania/wiki/%E3%83%81%E3%83%A3%E3%83%B3%E3%83%8D%E3%83%AB%E5%AE%9A%E7%BE%A9%E8%A1%A8

# Auto lane override details: https://osdn.net/projects/dtxmania/ticket/26338

import copy
from fractions import Fraction
import json
import math
from numpy import base_repr
import os
import re

import audio

dtx_bonus_mapping = {
    "leftcymbal": 0x01,
    "hihat": 0x02,
    "leftpedal": 0x03,
    "snare": 0x04,
    "hightom": 0x05,
    "bass": 0x06,
    "lowtom": 0x07,
    "floortom": 0x08,
    "rightcymbal": 0x09,
}
reverse_dtx_bonus_mapping = {dtx_bonus_mapping[k]: k for k in dtx_bonus_mapping if k != "auto"}

drum_mapping = {
    "hihat": 0x11,
    "snare": 0x12,
    "bass": 0x13,
    "hightom": 0x14,
    "lowtom": 0x15,
    "rightcymbal": 0x16,
    "floortom": 0x17,
    "leftcymbal": 0x1a,
    "leftpedal": 0x1b,
}

guitar_mapping = {
    "g_open": 0x20,
    "g_xxbxx": 0x21,
    "g_xgxxx": 0x22,
    "g_xgbxx": 0x23,
    "g_rxxxx": 0x24,
    "g_rxbxx": 0x25,
    "g_rgxxx": 0x26,
    "g_rgbxx": 0x27,
    "g_xxb": 0x21,
    "g_xgx": 0x22,
    "g_xgb": 0x23,
    "g_rxx": 0x24,
    "g_rxb": 0x25,
    "g_rgx": 0x26,
    "g_rgb": 0x27,
    "g_xxxyx": 0x93,
    "g_xxbyx": 0x94,
    "g_xgxyx": 0x95,
    "g_xgbyx": 0x96,
    "g_rxxyx": 0x97,
    "g_rxbyx": 0x98,
    "g_rgxyx": 0x99,
    "g_rgbyx": 0x9a,
    "g_xxxxp": 0x9b,
    "g_xxbxp": 0x9c,
    "g_xgxxp": 0x9d,
    "g_xgbxp": 0x9e,
    "g_rxxxp": 0x9f,
    "g_rxbxp": 0xa9,
    "g_rgxxp": 0xaa,
    "g_rgbxp": 0xab,
    "g_xxxyp": 0xac,
    "g_xxbyp": 0xad,
    "g_xgxyp": 0xae,
    "g_xgbyp": 0xaf,
    "g_rxxyp": 0xd0,
    "g_rxbyp": 0xd1,
    "g_rgxyp": 0xd2,
    "g_rgbyp": 0xd3,
}

bass_mapping = {
    "b_open": 0xa0,
    "b_xxbxx": 0xa1,
    "b_xgxxx": 0xa2,
    "b_xgbxx": 0xa3,
    "b_rxxxx": 0xa4,
    "b_rxbxx": 0xa5,
    "b_rgxxx": 0xa6,
    "b_rgbxx": 0xa7,
    "b_xxb": 0xa1,
    "b_xgx": 0xa2,
    "b_xgb": 0xa3,
    "b_rxx": 0xa4,
    "b_rxb": 0xa5,
    "b_rgx": 0xa6,
    "b_rgb": 0xa7,
    "b_xxxyx": 0xc5,
    "b_xxbyx": 0xc6,
    "b_xgxyx": 0xc8,
    "b_xgbyx": 0xc9,
    "b_rxxyx": 0xca,
    "b_rxbyx": 0xcb,
    "b_rgxyx": 0xcc,
    "b_rgbyx": 0xcd,
    "b_xxxxp": 0xce,
    "b_xxbxp": 0xcf,
    "b_xgxxp": 0xda,
    "b_xgbxp": 0xdb,
    "b_rxxxp": 0xdc,
    "b_rxbxp": 0xdd,
    "b_rgxxp": 0xde,
    "b_rgbxp": 0xdf,
    "b_xxxyp": 0xe1,
    "b_xxbyp": 0xe2,
    "b_xgxyp": 0xe3,
    "b_xgbyp": 0xe4,
    "b_rxxyp": 0xe5,
    "b_rxbyp": 0xe6,
    "b_rgxyp": 0xe7,
    "b_rgbyp": 0xe8,
}

dtx_mapping = {
    "auto": 0x61,
}
dtx_mapping.update(drum_mapping)
dtx_mapping.update(guitar_mapping)
dtx_mapping.update(bass_mapping)

reverse_dtx_mapping = {dtx_mapping[k]: k for k in dtx_mapping if k != "auto"}
reverse_dtx_mapping[0x1c] = "leftpedal"  # Because there are multiple mappings for the left pedal
reverse_dtx_mapping[0x18] = "hihat"  # Because there are multiple mappings for hihat

# TODO: How to handle ride? For now, just put it as an auto field
reverse_dtx_mapping[0x19] = "auto"  # RideCymbal

# For default note chips
reverse_dtx_mapping[0xb1] = "hihat"
reverse_dtx_mapping[0xb2] = "snare"
reverse_dtx_mapping[0xb3] = "bass"
reverse_dtx_mapping[0xb4] = "hightom"
reverse_dtx_mapping[0xb5] = "lowtom"
reverse_dtx_mapping[0xb6] = "rightcymbal"
reverse_dtx_mapping[0xb7] = "floortom"
reverse_dtx_mapping[0xb8] = "hihat"
reverse_dtx_mapping[0xbc] = "leftcymbal"
reverse_dtx_mapping[0xbd] = "leftpedal"
reverse_dtx_mapping[0xbe] = "leftpedal"

auto_play_ranges = list(range(0x61, 0x69 + 1)) + \
    list(range(0x70, 0x79 + 1)) + \
    list(range(0x80, 0x89 + 1)) + \
    list(range(0x90, 0x92 + 1))

default_note_events = list(range(0xb1, 0xb8 + 1)) + \
    list(range(0xbc, 0xbf + 1))  # b9 = ride, but we can't use the ride

drum_range = list(range(0x11, 0x1b + 1))

guitar_range = list(range(0x20, 0x27 + 1)) + \
    list(range(0x93, 0x9f + 1)) + \
    list(range(0xa9, 0xaf + 1)) + \
    list(range(0xd0, 0xd3 + 1))

bass_range = list(range(0xa0, 0xa7 + 1)) + \
    list(range(0xc5, 0xcf + 1)) + \
    list(range(0xda, 0xe8 + 1))


def convert_base36(val, padding):
    return base_repr(val, 36, padding=padding)[-padding:]


def create_json_from_dtx(params):
    def calculate_hold_duration(holds, measure_id, beat_id):
        for hold in holds:
            if hold[0][0] == measure_id and hold[0][1] == beat_id:
                return hold

        return None


    def calculate_wail_flag(wails, measure_id, beat_id):
        for wail in wails:
            if wail[0] == measure_id and wail[1] == beat_id:
                return 2 if wail[2] == 1 else 1

        return None


    def is_bonus_note(bonus_notes, measure_id, beat_id, match_note):
        for bonus in bonus_notes:
            if bonus[0] == measure_id and bonus[1] == beat_id and bonus[2] == match_note:
                return 1

        return 0


    def get_sound_id(filename):
        # TODO: Do this properly
        if filename[:2] in ["g_", "d_"]:
            filename = filename[2:]

        return int(os.path.splitext(os.path.basename(filename))[0], 16)


    def expand_measure(measure, division=192):
        split = [int(measure[i:i+2], 36) for i in range(0, len(measure), 2)]

        output = []
        for i in range(len(split)):
            output.append(split[i])
            output += [0] * ((division // (len(measure) // 2)) - 1)

        return output


    def generate_timestamps(parsed_lines, cur_bpm, bpm_list, division=192):
        timestamp_by_beat = {}
        cur_timestamp_step = 0.0
        cur_timestamp = 0.0
        for i in range(0, sorted(parsed_lines.keys())[-1] + 1):
            for j in range(0, division):
                if i not in timestamp_by_beat:
                    timestamp_by_beat[i] = {}

                timestamp_by_beat[i][j] = {
                    'timestamp': int(round(cur_timestamp * 300)),
                    'timestamp_ms': cur_timestamp
                }

                cur_timestamp += cur_timestamp_step

                if i in parsed_lines and 0x08 in parsed_lines[i] and parsed_lines[i][0x08][j] != 0:
                    cur_bpm = bpm_list[parsed_lines[i][0x08][j]]
                    cur_timestamp_step = (4 * (60 / cur_bpm)) / division

        return timestamp_by_beat


    def parse_dtx_to_intermediate(filename, params, sound_metadata, part, division=192):
        def get_sound_length(input_json, sound_id):
            if input_json and 'sound_lengths' in input_json and sound_id in input_json['sound_lengths']:
                return input_json['sound_lengths'][sound_id]

            return 0

        json_events = []

        if not filename or not os.path.exists(filename):
            return None, None, None, None, sound_metadata

        try:
            with open(filename, "r", encoding="shift-jis") as f:
                lines = [x.strip() for x in f if x.strip().startswith("#")]
        except:
            try:
                with open(filename, "r", encoding="utf-8") as f:
                    lines = [x.strip() for x in f if x.strip().startswith("#")]
            except:
                with open(filename, "r", encoding="utf-16") as f:
                    lines = [x.strip() for x in f if x.strip().startswith("#")]

        parsed_lines = {}
        bpm_list = {}
        wav_list = {}
        volume_list = {}
        cur_bpm = None
        comment_json = None
        guitar_holds_list = []
        bass_holds_list = []
        guitar_wail_list = []
        bass_wail_list = []
        bonus_notes = []

        for line in lines:
            event_str = line[1:]
            event_str = event_str[:min(event_str.index(':' if ':' in event_str else ' '), event_str.index(' '))]
            event_data = line[1 + len(event_str) + 1:].strip()

            if event_str == "TITLE":
                pass

            elif event_str == "ARTIST":
                pass

            elif event_str == "DLEVEL":
                pass

            elif event_str == "GLEVEL":
                pass

            elif event_str == "BLEVEL":
                pass

            elif event_str == "PREVIEW":
                pass

            elif event_str == "COMMENT":
                comment_json = json.loads(event_data)

            elif event_str.startswith("BPM"):
                if event_str == "BPM":
                    cur_bpm = float(event_data)
                    continue

                bpm_id = int(event_str[3:], 36)
                bpm_list[bpm_id] = float(event_data)

                if bpm_list[bpm_id] < 1:
                    bpm_list[bpm_id] = 1

                elif bpm_list[bpm_id] > 60000000:
                    bpm_list[bpm_id] = 60000000

            elif event_str.startswith("WAV"):
                wav_id = int(event_str[3:], 36)
                wav_list[wav_id] = event_data

            elif event_str.startswith("VOLUME"):
                wav_id = int(event_str[6:], 36)
                volume_list[wav_id] = int(event_data)

            else:
                measure_id = int(line[1:4])
                event_id = int(line[4:6], 16)

                # TODO: Add support for time signature command, and automatically generate measure and beat lines based on that when

                measure = expand_measure(event_data, division)

                if measure_id not in parsed_lines:
                    parsed_lines[measure_id] = {}

                parsed_lines[measure_id][event_id] = measure

                if event_id in reverse_dtx_mapping:
                    # print(reverse_dtx_mapping[event_id])
                    pass

                elif event_id == 0x01:
                    # BGM
                    pass

                elif event_id == 0xc2:
                    # End position
                    pass

                elif event_id == 0x08:
                    # BPM
                    pass

                elif event_id == 0x50:
                    # Show measure bar
                    pass

                elif event_id == 0x51:
                    # Show beat bar
                    pass

                elif event_id in [0x4c, 0x4d, 0x4e, 0x4f]:
                    # Bonus notes
                    for beat_id, val in enumerate(parsed_lines[measure_id][event_id]):
                        if val != 0 and val in reverse_dtx_bonus_mapping:
                            bonus_notes.append((measure_id, beat_id, reverse_dtx_bonus_mapping[val]))

                elif event_id in auto_play_ranges:
                    # Auto note
                    pass

                elif event_id == 0x28:
                    # Guitar Wail
                    for beat_id, val in enumerate(parsed_lines[measure_id][event_id]):
                        if val != 0:
                            guitar_wail_list.append((measure_id, beat_id, val))

                elif event_id == 0xa8:
                    # Bass Wail
                    for beat_id, val in enumerate(parsed_lines[measure_id][event_id]):
                        if val != 0:
                            bass_wail_list.append((measure_id, beat_id, val))

                elif event_id == 0x2c:
                    # Guitar long note
                    for beat_id, val in enumerate(parsed_lines[measure_id][event_id]):
                        if val != 0:
                            guitar_holds_list.append((measure_id, beat_id))


                elif event_id == 0x2d:
                    # Bass long note
                    for beat_id, val in enumerate(parsed_lines[measure_id][event_id]):
                        if val != 0:
                            bass_holds_list.append((measure_id, beat_id))

                else:
                    print("Unknown event id %02x" % event_id)
                    exit(1)

        if len(guitar_holds_list) % 2:
            print("Could not match all guitar long note starts with an end")
            exit(1)

        guitar_holds_list = [guitar_holds_list[i:i+2] for i in range(0, len(guitar_holds_list), 2)]

        if len(bass_holds_list) % 2:
            print("Could not match all bass long note starts with an end")
            exit(1)

        bass_holds_list = [bass_holds_list[i:i+2] for i in range(0, len(bass_holds_list), 2)]

        timestamp_by_beat = generate_timestamps(parsed_lines, cur_bpm, bpm_list, division)

        # Generate JSON using the timestamps generated
        base_chart = []
        drum_chart = []
        guitar_chart = []
        bass_chart = []

        for measure_id in parsed_lines:
            for event_id in parsed_lines[measure_id]:
                for beat_id, val in enumerate(parsed_lines[measure_id][event_id]):
                    timestamp = timestamp_by_beat[measure_id][beat_id]

                    if val == 0:
                        continue

                    if event_id in reverse_dtx_mapping or event_id in auto_play_ranges:
                        hold_timestamps = None
                        wail_misc = None

                        if event_id in drum_range:
                            target_chart = drum_chart

                        elif event_id in guitar_range:
                            target_chart = guitar_chart
                            hold_timestamps = calculate_hold_duration(guitar_holds_list, measure_id, beat_id)
                            wail_misc = calculate_wail_flag(guitar_wail_list, measure_id, beat_id)

                        elif event_id in bass_range:
                            target_chart = bass_chart
                            hold_timestamps = calculate_hold_duration(bass_holds_list, measure_id, beat_id)
                            wail_misc = calculate_wail_flag(bass_wail_list, measure_id, beat_id)

                        guitar_special = 0

                        if hold_timestamps:
                            guitar_special |= 2

                        if wail_misc:
                            guitar_special |= 1

                        note_str = "auto" if event_id in auto_play_ranges else reverse_dtx_mapping[event_id]

                        target_chart.append({
                            'name': "note",
                            'timestamp': timestamp['timestamp'],
                            'timestamp_ms': timestamp['timestamp_ms'],
                            'data': {
                                'sound_id': get_sound_id(wav_list[val]),
                                'note': note_str,
                                'note_length': get_sound_length(comment_json, val),
                                'hold_duration': timestamp_by_beat[hold_timestamps[1][0]][hold_timestamps[1][1]]['timestamp'] - timestamp_by_beat[hold_timestamps[0][0]][hold_timestamps[0][1]]['timestamp'] if hold_timestamps else 0,
                                'volume': volume_list[val] if val in volume_list else 127,
                                'wail_misc': wail_misc if wail_misc else 0,
                                'guitar_special': guitar_special,
                                'bonus_note': is_bonus_note(bonus_notes, measure_id, beat_id, note_str),
                                'auto_note': 1 if event_id in auto_play_ranges else 0,
                                'auto_volume': 1 if event_id in auto_play_ranges else 0,
                                'unk': 0,
                            }
                        })

                    elif event_id == 0x01:
                        # BGM
                        # Does this even really need to be handled?
                        pass

                    elif event_id == 0xc2:
                        # Start/end position
                        base_chart.append({
                            'name': "endpos" if val == 1 else "startpos",
                            'timestamp': timestamp['timestamp'],
                            'timestamp_ms': timestamp['timestamp_ms'],
                            'data': {}
                        })

                    elif event_id == 0x08:
                        # BPM
                        base_chart.append({
                            'name': "bpm",
                            'timestamp': timestamp['timestamp'],
                            'timestamp_ms': timestamp['timestamp_ms'],
                            'data': {
                                'bpm': bpm_list[val],
                            }
                        })

                    elif event_id == 0x50:
                        # Show measure bar
                        base_chart.append({
                            'name': "measure",
                            'timestamp': timestamp['timestamp'],
                            'timestamp_ms': timestamp['timestamp_ms'],
                            'data': {}
                        })

                    elif event_id == 0x51:
                        # Show beat bar
                        base_chart.append({
                            'name': "beat",
                            'timestamp': timestamp['timestamp'],
                            'timestamp_ms': timestamp['timestamp_ms'],
                            'data': {}
                        })

                    elif event_id in [0x28, 0xa8, 0x2c, 0x2d, 0x4c, 0x4d, 0x4e, 0x4f]:
                        # Ignore these, they aren't errors and are intentionally not handled here
                        pass

                    else:
                        print("Unknown event id %02x" % event_id)
                        exit(1)


        base_chart = {
            'header': {
                'difficulty': -1,
                'is_metadata': 1,
                'game_type': 0,
            },
            'beat_data': sorted(base_chart, key=lambda x:x['timestamp']),
        }

        drum_chart = {
            'header': {
                'difficulty': -1,
                'is_metadata': 0,
                'game_type': 0,
            },
            'beat_data': sorted(drum_chart, key=lambda x:x['timestamp']),
        }

        guitar_chart = {
            'header': {
                'difficulty': -1,
                'is_metadata': 0,
                'game_type': 1,
            },
            'beat_data': sorted(guitar_chart, key=lambda x:x['timestamp']),
        }

        bass_chart = {
            'header': {
                'difficulty': -1,
                'is_metadata': 0,
                'game_type': 2,
            },
            'beat_data': sorted(bass_chart, key=lambda x:x['timestamp']),
        }

        return base_chart, drum_chart, guitar_chart, bass_chart, sound_metadata

    def get_data(difficulty):
        output = {
            'drum': None,
            'guitar': None,
            'bass': None,
            'open': None,
            'guitar1': None,
            'guitar2': None
        }

        if 'input_split' not in params:
            return output

        for part in ['drum', 'guitar', 'bass', 'open', 'guitar1', 'guitar2']:
            if part in params['input_split'] and difficulty in params['input_split'][part]:
                filename = params['input_split'][part][difficulty]

                if filename and os.path.exists(filename):
                    output[part] = params['input_split'][part][difficulty]

        return output

    novice_data = get_data('nov')
    basic_data = get_data('bsc')
    adv_data = get_data('adv')
    ext_data = get_data('ext')
    master_data = get_data('mst')

    sound_metadata = {'sound_folder': params['sound_folder'] if 'sound_folder' in params else "", 'preview': "", 'bgm': {}, 'data': {}, 'guitar': [], 'drum': [], 'defaults': {}}

    def get_chart_data(data, sound_metadata, parts):
        metadatas = []

        chart_drum = None
        if "drum" in parts and 'drum' in data:
            metadata1, chart_drum, _, _, sound_metadata = parse_dtx_to_intermediate(data['drum'], params, sound_metadata, "drum")
            metadatas.append(metadata1)

        chart_guitar = None
        if "guitar" in parts and 'guitar' in data:
            metadata2, _, chart_guitar, _, sound_metadata = parse_dtx_to_intermediate(data['guitar'], params, sound_metadata, "guitar")
            metadatas.append(metadata2)

        chart_bass = None
        if "bass" in parts and 'bass' in data:
            metadata3, _,  _, chart_bass, sound_metadata = parse_dtx_to_intermediate(data['bass'], params, sound_metadata, "bass")
            metadatas.append(metadata3)

        chart_open = None
        # if "open" in parts and 'open' in data:
        #     metadata4, chart_bass, sound_metadata = parse_dtx_to_intermediate(data['open'], params, sound_metadata, "open")
        #     metadatas.append(metadata4)

        chart_guitar1 = None
        # if "guitar1" in parts and 'guitar1' in data:
        #     metadata5, chart_bass, sound_metadata = parse_dtx_to_intermediate(data['guitar1'], params, sound_metadata, "guitar1")
        #     metadatas.append(metadata5)

        chart_guitar2 = None
        # if "guitar2" in parts and 'guitar2' in data:
        #     metadata6, chart_bass, sound_metadata = parse_dtx_to_intermediate(data['guitar2'], params, sound_metadata, "guitar2")
        #     metadatas.append(metadata6)

        metadatas = [x for x in metadatas if x is not None]  # Filter bad metadata charts
        metadata = None if len(metadatas) == 0 else metadatas[0]

        return metadata, chart_drum, chart_guitar, chart_bass, chart_open, chart_guitar1, chart_guitar2, sound_metadata

    novice_metadata, novice_chart_drum, novice_chart_guitar, novice_chart_bass, novice_chart_open, novice_chart_guitar1, novice_chart_guitar2, sound_metadata = get_chart_data(novice_data, sound_metadata, params['parts'])
    basic_metadata, basic_chart_drum, basic_chart_guitar, basic_chart_bass, basic_chart_open, basic_chart_guitar1, basic_chart_guitar2, sound_metadata = get_chart_data(basic_data, sound_metadata, params['parts'])
    adv_metadata, adv_chart_drum, adv_chart_guitar, adv_chart_bass, adv_chart_open, adv_chart_guitar1, adv_chart_guitar2, sound_metadata = get_chart_data(adv_data, sound_metadata, params['parts'])
    ext_metadata, ext_chart_drum, ext_chart_guitar, ext_chart_bass, ext_chart_open, ext_chart_guitar1, ext_chart_guitar2, sound_metadata = get_chart_data(ext_data, sound_metadata, params['parts'])
    master_metadata, master_chart_drum, master_chart_guitar, master_chart_bass, master_chart_open, master_chart_guitar1, master_chart_guitar2, sound_metadata = get_chart_data(master_data, sound_metadata, params['parts'])

    # Create sound metadata file
    # Any notes not in the drums or guitar sound metadata fields should be added to both just in case
    sound_metadata_guitar = {
        "type": "GDXH",
        "version": 2,
        "gdx_type_unk1": 0,
        "gdx_volume_flag": 1,
        "defaults": {
            "default_snare": 0,
            "default_hihat": 0,
            "default_floortom": 65521,
            "default_leftcymbal": 65520,
            "default_rightcymbal": 0,
            "default_leftpedal": 65522,
            "default_lowtom": 0,
            "default_hightom": 0,
            "default_bass": 0
        },
        "entries": [],
    }

    for idx in sound_metadata['guitar']:
        if idx in sound_metadata['data']:
            sound_metadata_guitar['entries'].append(sound_metadata['data'][idx])

    for idx in list(set(sound_metadata['data'].keys()).difference(set(sound_metadata['guitar'] + sound_metadata['drum']))):
        if idx in sound_metadata['data']:
            sound_metadata_guitar['entries'].append(sound_metadata['data'][idx])

    sound_metadata_drums = {
        "type": "GDXG",
        "version": 2,
        "defaults": {
            "default_hihat": sound_metadata['defaults']['hihat'] if 'hihat' in sound_metadata['defaults'] else 0,
            "default_lowtom": sound_metadata['defaults']['lowtom'] if 'lowtom' in sound_metadata['defaults'] else 0,
            "default_snare": sound_metadata['defaults']['snare'] if 'snare' in sound_metadata['defaults'] else 0,
            "default_floortom": sound_metadata['defaults']['floortom'] if 'floortom' in sound_metadata['defaults'] else 0,
            "default_leftpedal": sound_metadata['defaults']['leftpedal'] if 'leftpedal' in sound_metadata['defaults'] else 0,
            "default_bass": sound_metadata['defaults']['bass'] if 'bass' in sound_metadata['defaults'] else 0,
            "default_leftcymbal": sound_metadata['defaults']['leftcymbal'] if 'leftcymbal' in sound_metadata['defaults'] else 0,
            "default_hightom": sound_metadata['defaults']['hightom'] if 'hightom' in sound_metadata['defaults'] else 0,
            "default_rightcymbal": sound_metadata['defaults']['rightcymbal'] if 'rightcymbal' in sound_metadata['defaults'] else 0,
        },
        "gdx_type_unk1": 0,
        "gdx_volume_flag": 1,
        "entries": [],
    }

    for idx in sound_metadata['drum']:
        if idx in sound_metadata['data']:
            sound_metadata_drums['entries'].append(sound_metadata['data'][idx])

    for idx in list(set(sound_metadata['data'].keys()).difference(set(sound_metadata['guitar'] + sound_metadata['drum']))):
        if idx in sound_metadata['data']:
            sound_metadata_drums['entries'].append(sound_metadata['data'][idx])

    metadata_charts = [x for x in [novice_metadata, basic_metadata, adv_metadata, ext_metadata, master_metadata] if x is not None]

    for chart in metadata_charts:
        chart['header']['difficulty'] = -1
        chart['header']['is_metadata'] = 1

    if 'drum' not in params['parts']:
        novice_chart_drum = None
        basic_chart_drum = None
        adv_chart_drum = None
        ext_chart_drum = None
        master_chart_drum = None

    if 'guitar' not in params['parts']:
        novice_chart_guitar = None
        basic_chart_guitar = None
        adv_chart_guitar = None
        ext_chart_guitar = None
        master_chart_guitar = None

    if 'bass' not in params['parts']:
        novice_chart_bass = None
        basic_chart_bass = None
        adv_chart_bass = None
        ext_chart_bass = None
        master_chart_bass = None

    if 'open' not in params['parts']:
        novice_chart_open = None
        basic_chart_open = None
        adv_chart_open = None
        ext_chart_open = None
        master_chart_open = None

    if 'guitar1' not in params['parts']:
        novice_chart_guitar1 = None
        basic_chart_guitar1 = None
        adv_chart_guitar1 = None
        ext_chart_guitar1 = None
        master_chart_guitar1 = None

    if 'guitar2' not in params['parts']:
        novice_chart_guitar2 = None
        basic_chart_guitar2 = None
        adv_chart_guitar2 = None
        ext_chart_guitar2 = None
        master_chart_guitar2 = None

    if 'guitar' not in params['parts'] and 'bass' not in params['parts']:
        sound_metadata_guitar = None

    def set_chart_difficulty(charts, difficulty):
        for chart in charts:
            if chart:
                chart['header']['difficulty'] = difficulty

    novice_charts = [novice_chart_drum, novice_chart_guitar, novice_chart_bass, novice_chart_open, novice_chart_guitar1, novice_chart_guitar2]
    basic_charts = [basic_chart_drum, basic_chart_guitar, basic_chart_bass, basic_chart_open, basic_chart_guitar1, basic_chart_guitar2]
    adv_charts = [adv_chart_drum, adv_chart_guitar, adv_chart_bass, adv_chart_open, adv_chart_guitar1, adv_chart_guitar2]
    ext_charts = [ext_chart_drum, ext_chart_guitar, ext_chart_bass, ext_chart_open, ext_chart_guitar1, ext_chart_guitar2]
    master_charts = [master_chart_drum, master_chart_guitar, master_chart_bass, master_chart_open, master_chart_guitar1, master_chart_guitar2]

    set_chart_difficulty(novice_charts, 0)
    set_chart_difficulty(basic_charts, 1)
    set_chart_difficulty(adv_charts, 2)
    set_chart_difficulty(ext_charts, 3)
    set_chart_difficulty(master_charts, 4)

    output_json = {
        "musicid": 0 if 'musicid' not in params or not params['musicid'] else params['musicid'],
        "charts": [x for x in ([metadata_charts[0]] if len(metadata_charts) > 0 else []) + ext_charts + master_charts + adv_charts + basic_charts + novice_charts if x is not None],
        "sound_metadata": {
            "guitar": sound_metadata_guitar,
            "drum": sound_metadata_drums,
        },
        "bgm": sound_metadata['bgm'],
        "preview": sound_metadata['preview'],
    }

    return json.dumps(output_json, indent=4, sort_keys=True)


def create_dtx_from_json(params):
    def generate_output_data(chart, game_type, division=192):
        def get_last_bpm(bpms, offset):
            last_bpm = 0

            for k in bpms:
                if k <= offset:
                    last_bpm = k

            return bpms[last_bpm]


        def get_nearest_beat(beats, timestamp):
            nearest_timestamp = 0

            for k in beats:
                if timestamp == k:
                    nearest_timestamp = k
                    break

                if abs(timestamp - k) < abs(timestamp - nearest_timestamp):
                    nearest_timestamp = k

            return beats[nearest_timestamp]


        def get_measures(events):
            measures = []
            for event in events[:]:
                if event['name'] == "measure": # Measure
                    measures.append(event)

                    for event2 in events:
                        if event2['name'] == "beat" and event['timestamp'] == event2['timestamp']: # Beat
                            events.remove(event2)

            return measures


        def get_bpm_per_measure(measures):
            bpm_per_measure = {}

            for i in range(0, len(measures) - 1):
                time_diff = measures[i+1]['timestamp'] - measures[i]['timestamp']
                bpm = 300 / (time_diff / 4 / 60)
                bpm_per_measure[measures[i]['timestamp']] = bpm

            return bpm_per_measure


        def get_bpm_list(bpm_per_measure):
            bpm_list = []

            for k in bpm_per_measure:
                bpm = bpm_per_measure[k]

                if bpm not in bpm_list:
                    bpm_list.append(bpm)

            return bpm_list


        def calculate_timestamp_mapping(events, measures, bpm_per_measure, division=192):
            cur_pos = 0
            mapping = {}

            last_measure = None

            for measure_idx, measure in enumerate(measures):
                last_measure = measure
                bpm = get_last_bpm(bpm_per_measure, measure['timestamp'])
                beat_duration = ((4 * (1/bpm)) * 60) / division

                for i in range(0, division):
                    mapping[cur_pos] = (measure_idx, i)
                    cur_pos = cur_pos + beat_duration

            last_event = sorted(events, key=lambda x:x['timestamp'])[-1]
            last_event_timestamp = last_event['timestamp_ms']

            while cur_pos < last_event_timestamp:
                measure_idx += 1

                bpm = get_last_bpm(bpm_per_measure, last_measure['timestamp'])
                beat_duration = ((4 * (1/bpm)) * 60) / division

                for i in range(0, division):
                    mapping[cur_pos] = (measure_idx, i)
                    cur_pos = cur_pos + beat_duration

            return mapping


        def get_events_from_chart(chart):
            events = []

            for event in sorted(chart['beat_data'], key=lambda x:x['timestamp']):
                events.append(event)

            return events


        def simplify_measures(chart):
            def can_divide_measure(measure, n):
                div = len(measure) // n

                for j in range(0, div):
                    for k in range(1, n):
                        if measure[(j * n) + k] != 0:
                            return False

                return True

            for measure_idx in output_data:
                for event in list(output_data[measure_idx].keys()):
                    # Remove empty measures
                    if len([x for x in output_data[measure_idx][event] if x != 0]) == 0:
                        del output_data[measure_idx][event]
                        continue

                    # Simplify all measures that are evenly divisible
                    div_size = 1
                    for i in range(1, len(output_data[measure_idx][event]) + 1):
                        if len(output_data[measure_idx][event]) % i != 0:
                            continue

                        if can_divide_measure(output_data[measure_idx][event], i):
                            div_size = i

                    output_data[measure_idx][event] = [output_data[measure_idx][event][x] for x in range(0, len(output_data[measure_idx][event]), div_size)]

            return output_data

        def generate_hold_release_events(events):
            _events = []
            for event in events:
                _events.append(event)

                if event['name'] == "note":
                    if 'guitar_special' in event['data'] and event['data']['guitar_special'] & 0x02:
                        # Long note start
                        new_note = copy.deepcopy(event)
                        new_note['name'] = "_note_start"

                        _events.append(new_note)

                        # Long note end
                        new_note = copy.deepcopy(event)
                        new_note['name'] = "_note_release"

                        timestamp_offset = 0
                        while True:
                            new_timestamp = event['timestamp'] + event['data']['hold_duration'] - timestamp_offset

                            found_note = False
                            for event2 in events:
                                if event2['timestamp'] == new_timestamp and event2['name'] == "note":
                                    found_note = True
                                    timestamp_offset += 1
                                    break

                            if not found_note:
                                break

                        new_note['timestamp'] = new_timestamp
                        new_note['timestamp_ms'] = new_timestamp / 300

                        _events.append(new_note)

            return _events


        def generate_sound_id_map(events):
            used_sound_ids = {}
            sound_id_lookup = {}

            cur_sound_id = 1

            for event in events:
                if event['name'] == "note":
                    sound_key = "%d_%d" % (event['data']['sound_id'], event['data'].get('note_length', 0))

                    if sound_key not in sound_id_lookup:
                        sound_id_lookup[sound_key] = cur_sound_id
                        used_sound_ids[cur_sound_id] = {
                            'sound_id': event['data']['sound_id'],
                            'filename': "%04x" % event['data']['sound_id'],
                            'duration': event['data'].get('note_length', 0)
                        }
                        cur_sound_id += 1

                    event['data']['sound_id'] = sound_id_lookup[sound_key]

            return events, used_sound_ids


        events = get_events_from_chart(chart)
        events, used_sound_ids = generate_sound_id_map(events)
        events = generate_hold_release_events(events)
        measures = get_measures(events)
        bpm_per_measure = get_bpm_per_measure(measures)
        bpm_list = get_bpm_list(bpm_per_measure)
        mapping = calculate_timestamp_mapping(events, measures, bpm_per_measure, division)

        display_bar = True

        output_data = {}
        sound_keys = [None]
        sound_info = {}
        for event in events:
            measure_idx, beat_idx = get_nearest_beat(mapping, event['timestamp_ms'])

            if measure_idx not in output_data:
                output_data[measure_idx] = {
                    0x08: [0x00] * division, # BPM
                    0x50: [0x00] * division, # Show measure bar
                    0x51: [0x00] * division, # Show beat bar
                    0x2c: [0x00] * division, # Guitar long note
                    0x2d: [0x00] * division, # Bass long note
                    0xc2: [0x00] * division, # End position
                    0x28: [0x00] * division, # Guitar Wail
                    0xa8: [0x00] * division, # Bass Wail
                    0x4c: [0x00] * division, # Bonus note #1
                    0x4d: [0x00] * division, # Bonus note #2
                    0x4e: [0x00] * division, # Bonus note #3
                    0x4f: [0x00] * division, # Bonus note #4
                }

                for k in reverse_dtx_mapping:
                    output_data[measure_idx][k] = [0x00] * division

                for k in auto_play_ranges:
                    output_data[measure_idx][k] = [0x00] * division

            if event['timestamp'] in bpm_per_measure:
                output_data[measure_idx][0x08][beat_idx] = bpm_list.index(bpm_per_measure[event['timestamp']]) + 1

            if event['name'] == "baron":
                display_bar = True

            elif event['name'] == "baroff":
                display_bar = False

            elif event['name'] == "endpos":
                output_data[measure_idx][0xc2][beat_idx] = 0x01

            elif event['name'] == "measure":
                output_data[measure_idx][0x50][beat_idx] = 0x01 if display_bar else 0x00

            elif event['name'] == "beat":
                output_data[measure_idx][0x51][beat_idx] = 0x01 if display_bar else 0x00

            elif event['name'] == "note":
                sound_key = "%04d_%03d" % (
                    event['data']['sound_id'],
                    event['data']['volume'],
                )

                if sound_key not in sound_keys:
                    sound_keys.append(sound_key)
                    sound_id = sound_keys.index(sound_key)
                    sound_info[sound_id] = {
                        'sound_id': event['data']['sound_id'],
                        'volume': event['data']['volume'],
                    }

                sound_id = sound_keys.index(sound_key)

                if event['data']['note'] == "auto":
                    for note in auto_play_ranges:
                        if output_data[measure_idx][note][beat_idx] == 0:
                            break

                    output_data[measure_idx][note][beat_idx] = sound_id

                else:
                    output_data[measure_idx][dtx_mapping[event['data']['note']]][beat_idx] = sound_id

                if 'guitar_special' in event['data'] and event['data']['guitar_special'] & 0x01:
                    if event['data']['wail_misc'] == 2:
                        # Down wail
                        # Currently down wailing isn't supported by any simulator,
                        # so just use up wail's commands for now
                        wail_field = {
                            'd': -1,
                            'g': 0x28,
                            'b': 0xa8,
                            'o': 0x28,
                            'g1': 0x28,
                            'g2': 0xa8,
                        }[game_type]

                        wail_direction = 2

                    else:  # 0, 1, ?
                        # Up wail
                        wail_field = {
                            'd': -1,
                            'g': 0x28,
                            'b': 0xa8,
                            'o': 0x28,
                            'g1': 0x28,
                            'g2': 0xa8,
                        }[game_type]

                        wail_direction = 1

                    output_data[measure_idx][wail_field][beat_idx] = wail_direction

                if event['data'].get('bonus_note') and event['data']['note'] in dtx_bonus_mapping:
                    bonus_note_lane = 0x4f

                    while bonus_note_lane >= 0x4c:
                        if output_data[measure_idx][bonus_note_lane][beat_idx] != 0:
                            bonus_note_lane -= 1
                            continue

                        output_data[measure_idx][bonus_note_lane][beat_idx] = dtx_bonus_mapping[event['data']['note']]
                        break

                    if bonus_note_lane < 0x4c:
                        print("Couldn't find enough bonus note lanes")

        for event in events:
            longnote_fields = {
                'd': None,
                'g': 0x2c,
                'b': 0x2d,
                'o': 0x2c,
                'g1': 0x2c,
                'g2': 0x2d,
            }[game_type]

            if not longnote_fields:
                break

            if event['name'] == "_note_start":
                measure_idx, beat_idx = get_nearest_beat(mapping, event['timestamp_ms'])
                output_data[measure_idx][longnote_fields][beat_idx] = 0x01

            elif event['name'] == "_note_release":
                measure_idx, beat_idx = get_nearest_beat(mapping, event['timestamp_ms'])

                check_events = {
                    'g': guitar_range,
                    'b': bass_range,
                    'o': guitar_range,
                    'g1': guitar_range,
                    'g2': bass_range,
                }[game_type]

                while True:
                    updated = False

                    for check_event in check_events:
                        if measure_idx not in output_data or check_event not in output_data[measure_idx]:
                            continue

                        if output_data[measure_idx][check_event][beat_idx] != 0:
                            if beat_idx == 0:
                                measure_idx -= 1
                                beat_idx = division

                            beat_idx -= 1
                            updated = True
                            break

                    if not updated:
                        if measure_idx not in output_data:
                            output_data[measure_idx] = {
                                longnote_fields: [0x00] * division, # Long note
                            }

                        output_data[measure_idx][longnote_fields][beat_idx] = 0x01
                        break

        return {
            'data': simplify_measures(output_data),
            'sound_ids': used_sound_ids,
            'bpms': bpm_list,
            'sound_info': sound_info,
        }


    output_json = {}

    input_json = json.loads(params['input'])
    output_folder = params.get('output', "")

    if 'format' in input_json:
        origin_format = "_%s" % input_json['format'].lower()
    else:
        origin_format = ""

    for chart in input_json['charts']:
        difficulty = ['nov', 'bsc', 'adv', 'ext', 'mst'][chart['header']['difficulty']]
        game_initial = ['d', 'g', 'b', 'o', 'g1', 'g2'][chart['header']['game_type']]
        sound_initial = ['drum', 'guitar', 'guitar', 'guitar', 'guitar', 'guitar'][chart['header']['game_type']]
        bgm_filename = ['_gbk.wav', 'd_bk.wav', 'dg_k.wav', 'd_bk.wav', 'd_bk.wav', 'd_bk.wav'][chart['header']['game_type']]

        output_data = generate_output_data(chart, game_initial)

        output_filename = "%s_%04d_%s%s.dtx" % (game_initial,
                                            input_json.get('musicid', 0),
                                            difficulty,
                                            origin_format)


        print("Saving", output_filename)
        output_filename = os.path.join(output_folder, output_filename)

        with open(output_filename, "w") as outfile:
            outfile.write("""#TITLE: (no title)
#ARTIST: (no artist)
#DLEVEL: 1
#GLEVEL: 1
#BLEVEL: 1\n""")


            comment_json = {
                'sound_lengths': {}
            }

            for k in output_data['sound_ids']:
                if output_data['sound_ids'][k]['duration']:
                    comment_json['sound_lengths'][k] = output_data['sound_ids'][k]['duration']

            if comment_json['sound_lengths']:
                outfile.write("#COMMENT %s\n" % json.dumps(comment_json))

            sound_metadata = params.get('sound_metadata', None)
            for k in sorted(output_data['sound_info'].keys()):
                wav_filename = "%s_%04x.wav" % (sound_initial[0], output_data['sound_ids'][output_data['sound_info'][k]['sound_id']]['sound_id'])

                outfile.write("#WAV%s: %s\n" % (base_repr(k, 36, padding=2).upper()[-2:], wav_filename))
                outfile.write("#VOLUME%s: %d\n" % (base_repr(k, 36, padding=2).upper()[-2:], round((output_data['sound_info'][k]['volume'] / 127) * 100)))
            #     output.append("#PAN%s %d" % (base_repr(int(k), 36, padding=2).upper()[-2:], output_data['sound_info'][k]['pan']))


            sound_initial = ""
            outfile.write("""#WAVZZ: %s
#00001: ZZ
#000C2: 02\n""" % (os.path.join(sound_initial, bgm_filename)))

            outfile.write("#BPM %f\n" % output_data['bpms'][0])
            for i, bpm in enumerate(output_data['bpms']):
                outfile.write("#BPM%s %f\n" % (base_repr(i + 1, 36, padding=2).upper()[-2:], output_data['bpms'][i]))


            for measure_idx in output_data['data']:
                for eidx in output_data['data'][measure_idx]:
                    if eidx == 0x02:
                        outfile.write("#%03d%02X: %f\n" % (measure_idx, eidx, output_data['data'][measure_idx][eidx]))

                    else:
                        outfile.write("#%03d%02X: %s\n" % (measure_idx, eidx, "".join([convert_base36(x, 2) for x in output_data['data'][measure_idx][eidx]])))


class DtxFormat:
    @staticmethod
    def get_format_name():
        return "DTX"

    @staticmethod
    def to_json(params):
        return create_json_from_dtx(params)

    @staticmethod
    def to_chart(params):
        return create_dtx_from_json(params)

    @staticmethod
    def is_format(filename):
        return False


def get_class():
    return DtxFormat
