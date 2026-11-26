"""The local model's instructions and output schema. No Home Assistant imports, so it can be tested on its own.

like, save_to_playlist and cancel from the model are only kept when router.py's rules back them."""

ACTIONS = ["on", "off", "brightness", "music", "music_only", "movie", "pause", "resume", "next", "stop",
           "volume_up", "volume_down", "like", "save_to_playlist", "cancel", "none"]

EXAMPLES = (
    'switch on the amp -> {"a":"on","d":"Amp","q":"","n":0}\n'
    'kill everything -> {"a":"off","d":"everything","q":"","n":0}\n'
    'play some Daft Punk on the pi -> {"a":"music","d":"Pi","q":"Daft Punk","n":0}\n'
    'just play Hallelujah -> {"a":"music_only","d":"","q":"Hallelujah","n":0}\n'
    'play only Creep by Radiohead -> {"a":"music_only","d":"","q":"Creep by Radiohead","n":0}\n'
    'play Yesterday by the Beatles -> {"a":"music","d":"","q":"Yesterday by the Beatles","n":0}\n'
    'put on The Matrix -> {"a":"movie","d":"TV","q":"The Matrix","n":0}\n'
    'next track -> {"a":"next","d":"","q":"","n":0}\n'
    'make the decor lamp half as bright -> {"a":"brightness","d":"Decor light","q":"","n":50}\n'
    'i love this song -> {"a":"like","d":"","q":"","n":0}\n'
    'add this to my workout playlist -> {"a":"save_to_playlist","d":"","q":"workout","n":0}\n'
    'Claude stop -> {"a":"cancel","d":"","q":"","n":0}\n'
    'what is the capital of Peru -> {"a":"none","d":"","q":"","n":0}\n'
    'well i dunno -> {"a":"none","d":"","q":"","n":0}\n'
    "A user may speak Hungarian. Keep q in its original language.\n"
    'kapcsold le a dekor lámpát -> {"a":"off","d":"Decor light","q":"","n":0}\n'
    'kapcsolj le mindent -> {"a":"off","d":"everything","q":"","n":0}\n'
    'játssz valami Beatles számot -> {"a":"music","d":"","q":"Beatles","n":0}\n'
    'csak a Hey Jude-ot játszd -> {"a":"music_only","d":"","q":"Hey Jude","n":0}\n'
    'tedd be a Mátrix filmet -> {"a":"movie","d":"TV","q":"Mátrix","n":0}\n'
    'indítsd el a Ponyvaregényt -> {"a":"movie","d":"TV","q":"Ponyvaregény","n":0}\n'
    'indítsd el a Pulp Fiction filmet -> {"a":"movie","d":"TV","q":"Pulp Fiction","n":0}\n'
    'tedd be a Keresztapát -> {"a":"movie","d":"TV","q":"Keresztapa","n":0}\n'
    'indíts egy kis Mozartot -> {"a":"music","d":"","q":"Mozart","n":0}\n'
    'játssz klasszikus zenét -> {"a":"music","d":"","q":"klasszikus zene","n":0}\n'
    'következő szám -> {"a":"next","d":"","q":"","n":0}\n'
    'halkítsd le -> {"a":"volume_down","d":"","q":"","n":0}\n'
    'hangosíts húsz százalékot -> {"a":"volume_up","d":"","q":"","n":20}\n'
    'halkítsd le harmincra -> {"a":"volume_down","d":"","q":"","n":30}\n'
    'folytasd -> {"a":"resume","d":"","q":"","n":0}\n'
    'állítsd le a zenét -> {"a":"stop","d":"","q":"","n":0}\n'
    'szünet -> {"a":"pause","d":"","q":"","n":0}\n'
    'ez tetszik -> {"a":"like","d":"","q":"","n":0}\n'
    'lájkold ezt a számot -> {"a":"like","d":"","q":"","n":0}\n'
    'tedd a kedvencekhez ezt a számot -> {"a":"like","d":"","q":"","n":0}\n'
    'kedvencekhez -> {"a":"like","d":"","q":"","n":0}\n'
    'mentsd el a rock listába -> {"a":"save_to_playlist","d":"","q":"rock","n":0}\n'
    'tedd fel ezt a nyári lejátszási listára -> {"a":"save_to_playlist","d":"","q":"nyári","n":0}\n'
    'rakd be ezt a számot az edzős listámba -> {"a":"save_to_playlist","d":"","q":"edzős","n":0}\n'
    'csinálj egy lejátszási listát pörgős számokból -> {"a":"none","d":"","q":"","n":0}\n'
    'indíts el egy rock playlistet -> {"a":"music","d":"","q":"rock playlist","n":0}\n'
    'Claude állj -> {"a":"cancel","d":"","q":"","n":0}\n'
    'hagyd abba Claude -> {"a":"cancel","d":"","q":"","n":0}\n'
    'mégse -> {"a":"cancel","d":"","q":"","n":0}\n'
    'milyen idő lesz holnap -> {"a":"none","d":"","q":"","n":0}\n'
    'mit is akartam -> {"a":"none","d":"","q":"","n":0}\n'
)


def system(devices, speakers):
    return (
        "Smart home command parser. Output JSON only. Devices: " + ", ".join(devices) + ". Speakers: "
        + ", ".join(speakers) + ". a is one of " + " ".join(ACTIONS) + ". d is a device or speaker or empty. "
        "q is a song, artist, film or playlist name or empty. n is a percent or 0. "
        "like: favourite the playing song. save_to_playlist: add the playing song to playlist q, only when a playlist (lista) is said. "
        "cancel: stop what Claude is doing. none: anything else, like questions.\n"
        "Examples:\n" + EXAMPLES + "/no_think"
    )


def schema(devices, speakers):
    return {
        "type": "object",
        "properties": {
            "a": {"enum": ACTIONS},
            "d": {"enum": [*devices, *speakers, ""]},
            "q": {"type": "string", "maxLength": 50},
            "n": {"type": "integer"},
        },
        "required": ["a", "d", "q", "n"],
    }

