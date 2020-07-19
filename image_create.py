#!/usr/bin/env python3
"""
Matt Manzi
Created: 2020-07-17

Overlay each subject image on each background N times, at random positions and
sizes, and generate the relevant annotation for Apple's CreateML.  The generated
image file will have the format of the background image that is used.

Annotation Format:
[
    {
        "annotation": [
            {
                "label": "%LABEL%",
                "coordinates": {
                    "y": %TOP-LEFT-Y%,
                    "x": %TOP-LEFT-X%,
                    "width": %WIDTH%,
                    "height": %HEIGHT%
                }
            }
        ],
        "imagefilename": "%FILENAME%"
    }
]

TODOS:
    - multiprocessing for multi (split photo batches by background)
    - (future) subject image rotation
"""

import logging, os, json, random, copy
from argparse import ArgumentParser
from PIL import Image




################################## CONSTANTS ##################################

# generation params
N = 10
SCALE_MAX = 80
SCALE_MIN = 5

# fs structure
IMG_DIR = "img"
IMG_SUBJ = "subject"
IMG_BKGD = "background"
IMG_DEST = "generated"
ANO_FILE = "annotations.json"

# other
VERBOSITY = logging.WARNING




#################################### CODE ####################################


#### MARK: Globals Init

logging.basicConfig(
    level=VERBOSITY,
    format="[%(asctime)s] %(name)s %(levelname)s: %(message)s"
)
log = logging.getLogger("Image-Superimposer")

parser = ArgumentParser(description="""
Generates composite photos for CreateML object recognition from subject and
background images.""")
parser.add_argument("label",
    help="the name of the label for the subject's annotation")
parser.add_argument("-n", "--variations",
    type=int,
    default=N,
    help="the number of variations to make with each image and background pair")
parser.add_argument("--no-scale",
    action="store_true",
    help="do not change the scale of the subject image (unexepected behavior \
    for subject image larger than background image)")
parser.add_argument("-v", "--verbose",
    action="count",
    default=0,
    help="increase the verbosity of log output (takes precedence over --quiet)")
parser.add_argument("-q", "--quiet",
    action="count",
    default=0,
    help="decrease the verbosity of log output (--verbose takes precedence)")
args = parser.parse_args()

# set user log level
if args.verbose:
    log.setLevel(max(VERBOSITY - (args.verbose * logging.DEBUG), logging.DEBUG))
elif args.quiet:
    log.setLevel(VERBOSITY + (args.quiet * logging.DEBUG))


#### MARK: Script Execution

def main():

    # set annotation label
    ano_tmp = {
        "annotation": [
            {
                "label": args.label,
                "coordinates": {
                    "y": None,
                    "x": None,
                    "width": None,
                    "height": None
                }
            }
        ],
        "imagefilename": None
    }
    annotations = []

    # load image folders
    img_dir = os.path.join(os.getcwd(), IMG_DIR)
    subj_dir = os.path.join(img_dir, IMG_SUBJ)
    background_dir = os.path.join(img_dir, IMG_BKGD)
    dest_dir = os.path.join(img_dir, IMG_DEST)

    # ensure dest directory exists
    try:
        os.mkdir(dest_dir)

    except FileExistsError:
        log.debug("Destination directory %s exists, no action", dest_dir)


    log.info("===================Begin Image Processing===================")


    # for each background
    for bkgd_file in os.listdir(background_dir):
        log.debug("Opening background file: %s", bkgd_file)

        # choose extension from background, as per rules of paste
        ext = bkgd_file.split(".")[-1]
        log.debug("Set output extension: %s", ext)

        bkgd_p = Image.open(os.path.join(background_dir, bkgd_file))
        bkgd_file = bkgd_file.rstrip("." + ext)
        log.debug("Opened background: %s (ext stripped)", bkgd_file)


        # for each subject
        for subj_file in os.listdir(subj_dir):
            log.debug("Opening subject file: %s", subj_file)

            subj_p = Image.open(os.path.join(subj_dir, subj_file))
            subj_file = subj_file.rstrip("." + ext)
            log.debug("Opened subject: %s (no ext)", subj_file)


            # for N variations
            for i in range(args.variations):
                log.debug("Started variation: %d", i)

                ano = copy.deepcopy(ano_tmp)
                log.debug("Created template annotation deep copy")

                # compose filename
                gen_filename = ".".join([subj_file, bkgd_file, str(i), ext])
                ano["imagefilename"] = gen_filename
                log.debug("Set generated filename: %s", gen_filename)

                # create composite image
                subj_tmp = subj_p
                if not args.no_scale:
                    log.debug("Will scale subject")
                    subj_tmp = scale_to_background(subj_tmp, bkgd_p, ano)

                pos_x, pos_y = place_on_background(subj_tmp, bkgd_p, ano)

                bkgd_tmp = bkgd_p.copy()
                bkgd_tmp.paste(subj_tmp, (pos_x, pos_y))

                # save new image and annotation
                try:
                    bkgd_tmp.save(os.path.join(dest_dir, gen_filename))
                    annotations.append(ano)

                except ValueError:
                    log.info("Unable to determine file format")
                    log.warning("Skipping: %s", gen_filename)

                except OSError:
                    log.info("Unable to write composite image to disk: %s",
                        gen_filename)
                    log.warning("Skipping: %s", gen_filename)

                finally:
                    # close temporary images
                    bkgd_tmp.close()
                    if subj_tmp != subj_p:
                        subj_tmp.close()
                    log.debug("Closed temporary images")


            # done with this subject
            subj_p.close()
            log.debug("Closed subject: %s", subj_file)


        # done with this background
        bkgd_p.close()
        log.debug("Closed background: %s", bkgd_file)


    log.info("====================End Image Processing====================")

    # store annotations
    annotations_file = open(os.path.join(dest_dir, ANO_FILE), "w")
    annotations_file.write(json.dumps(annotations))
    annotations_file.close()
    log.debug("Wrote annotations to file: %s", ANO_FILE)


#### MARK: Helper functions

def scale_to_background(subj_p, bkgd_p, annotation):
    """Scale the subject image up or down, relative to the background

    Returns:
        Image
        in the new size
    """
    subj_w, subj_h = subj_p.size
    bkgd_w, bkgd_h = bkgd_p.size

    # pick a random scale (height as percent of background image size)
    scale = random.randint(SCALE_MIN, SCALE_MAX) / 100
    log.debug("Set subject scale: %f", scale)
    subj_w = int(subj_w * (bkgd_h * scale) / subj_h)
    subj_h = int(bkgd_h * scale)
    log.debug("Set subject sizes (w x h): (%d, %d)", subj_w, subj_h)

    # update annotation
    annotation["annotation"][0]["coordinates"]["width"] = subj_w
    annotation["annotation"][0]["coordinates"]["height"] = subj_h
    log.debug("Updated annotation sizes")

    return subj_p.resize((subj_w, subj_h))




def place_on_background(subj_p, bkgd_p, annotation):
    """Chooses a position for the subject image on the background

    Returns:
        (int, int)
        the (x, y) coordinates of the top-left subject image corner
    """
    subj_w, subj_h = subj_p.size
    bkgd_w, bkgd_h = bkgd_p.size

    # pick a random position for top-left corner (ensure subject stays
    # in bounds of background)
    position_x = random.randint(0, bkgd_w - subj_w)
    position_y = random.randint(0, bkgd_h - subj_h)
    log.debug("Set subject position (x, y): (%d, %d)", position_x, position_y)

    # update annotation
    annotation["annotation"][0]["coordinates"]["y"] = position_y
    annotation["annotation"][0]["coordinates"]["x"] = position_x
    log.debug("Updated annotation position")

    return (position_x, position_y)




main()
