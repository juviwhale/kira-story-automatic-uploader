import os
from io import BytesIO
import re
from typing import List, Tuple

import requests

import modules.scripts as scripts
import gradio as gr
from modules import paths, script_callbacks
from modules.shared import opts, OptionInfo
import random
import string
from PIL import PngImagePlugin
from modules.ui_components import FormGroup

CHARACTERS = ["Kira", "Juviwhale"]

STORIES = {
    "My Friend The Alien": {
        "pages": ["1", "2", "3"],
        "poses": ["Running", "Sitting Looking Up"],
    },
    "The Littlest Alien": {
        "pages": ["1", "2", "3", "4"],
        "poses": ["Talking", "Looking Backwards"],
    },
}


# Todo: Prompicate metadata from inpainting+texttoimage

def get_generation_info(processed):
    regex = r"Steps:.*$"
    prompt = processed.prompt
    neg_prompt = processed.negative_prompt
    info = re.findall(regex, processed.info, re.M)[0]
    input_dict = dict(item.split(": ") for item in str(info).split(", "))
    steps = int(input_dict["Steps"])
    seed = int(input_dict["Seed"])
    sampler = input_dict["Sampler"]
    cfg_scale = float(input_dict["CFG scale"])
    size = tuple(map(int, input_dict["Size"].split("x")))
    model_hash = input_dict["Model hash"]
    model = input_dict["Model"]
    return {
        "prompt": prompt,
        "negative_prompt": neg_prompt,
        "steps": int(steps),
        "seed": int(seed),
        "sampler": sampler,
        "cfg_scale": float(cfg_scale),
        "size": size,
        "model_hash": model_hash,
        "model": model,
    }


def get_image_path(character, story, page, pose):
    rand_str = ''.join(random.choices(string.ascii_lowercase, k=5))
    return f"{character}/{story}/{page}/{pose}/{rand_str}.png"


def get_signed_url_for_prompt_image(path: str, service_url: str, api_key: str):
    """Returns a signed URL for uploading an image to Google Cloud Storage"""
    headers = {'Content-Type': 'application/json', 'X-API-KEY': api_key}
    body = {"path": path}
    response = requests.post(f"{service_url}/image_upload_location", json=body, headers=headers)
    response_json = response.json()
    print(response_json)
    return response_json['url']


def upload_image_to_gs(image, signed_url):
    """Uploads an image to Google Storage using a signed URL"""
    response = requests.put(signed_url, data=image)
    if response.status_code != 200:
        raise Exception(f"Failed to upload image to Google Storage. Status code: {response.status_code}")
    return response


def build_status_info(character, story, page, pose, image_path, image_id, was_successful):
    """Builds the status info for the upload status panel"""
    status_color = "green" if was_successful else "red"
    submission_status = "Submitted Successfully" if was_successful else "Submission Failed"
    status_info = f'<br><b style="color:{status_color};">{submission_status}</b>&nbsp;&nbsp;'
    status_info += f"(<small>ID:</small>&nbsp;{image_id}&nbsp;&nbsp;"
    status_info += f"<small>Character:</small>&nbsp;{character}&nbsp;&nbsp;"
    status_info += f"<small>Story:</small>&nbsp;{story}&nbsp;&nbsp;"
    status_info += f"<small>Pose:</small>&nbsp;{pose}&nbsp;)&nbsp;"
    return status_info


def kira_uploader_click(status_info):
    """Handles the click event for the Kira Uploader button"""
    global generated_images
    print(f"{len(generated_images)} images in generated_images")

    # Check if minimum API config is available
    if not opts.kira_image_submitter_service_url or not opts.kira_image_submitter_service_api_key:
        status_info = f'<b style="color:red;">Please configure the API key and service URL in the settings</b>'
        return status_info

    # Check if there are any images to submit
    if len(generated_images) == 0:
        status_info = f'<b style="color:red;">No images found to be submitted</b>'
        return status_info

    print(f"Uploading {len(generated_images)} images to Google Storage")
    status_info = f"<b>Images Submitted:</b></br>"
    for image in generated_images:
        # Extract Story info from image
        story = image.info.get('story', '-')
        character = image.info.get('character', '-')
        page = image.info.get('page', '-')
        pose = image.info.get('pose', '-')
        notes = image.info.get('notes', '')

        # Add metadata to image
        pnginfo_data = PngImagePlugin.PngInfo()
        for k, v in image.info.items():
            pnginfo_data.add_text(k, str(v))

        buffer = BytesIO()
        image.save(buffer, "png", pnginfo=pnginfo_data)
        image_bytes = buffer.getvalue()

        service_url = str(opts.kira_image_submitter_service_url)
        api_key = str(opts.kira_image_submitter_service_api_key)

        print(f"Service URL: {service_url}")
        print(f"Api key {api_key}")
        if not service_url or not api_key:
            print("Cannot save image to GCS. Service URL or API Key not set.")
            return False

        # Upload to GCS
        image_path = get_image_path(character, story, page, pose)
        image_id = image_path.split("/")[-1].split(".")[0]

        was_successful = False
        try:
            signed_url = get_signed_url_for_prompt_image(image_path, service_url, api_key)
            print(f"Signed URL: {signed_url}")
            upload_image_to_gs(image_bytes, signed_url)
            print(f"File Uploaded to {image_path}")
            was_successful = True
        except Exception as e:
            print(f"Failed to get signed URL for image. Error: {e}")
            return False

        # Update status info
        status_info += build_status_info(character, story, page, pose, image_path, image_id, was_successful)

    # Clear generated images
    generated_images = []
    return status_info


all_btns: List[Tuple[gr.Button, ...]] = []
submit_symbol = '\U0001f680'  # 🚀❌⬆️🕺🐙⭐️🏹🎯🚀🛰️🏁
tab_current = None
generated_images = []


class Scripts(scripts.Script):

    def after_component(self, component, **kwargs):
        global tab_current, kira_uploader_status_info
        element = kwargs.get("elem_id")
        if element == "extras_tab" and tab_current is not None:
            kira_uploader_click_button = gr.Button(value=submit_symbol)
            kira_uploader_click_button.click(
                fn=kira_uploader_click,
                inputs=[kira_uploader_status_info],
                outputs=[kira_uploader_status_info],
                _js=tab_current + "_kira_uploader_addEventListener",
            )
            tab_current = None
        elif element in ["txt2img_gallery", "img2img_gallery"]:
            tab_current = element.split("_", 1)[0]
            with gr.Column():
                kira_uploader_status_info = gr.HTML(elem_id=tab_current + "_kira_uploader_status_info")

    def title(self):
        return "Save to Google Storage"

    def show(self, is_img2img):
        return scripts.AlwaysVisible

    def ui(self, is_img2img):

        def gr_show(visible=True):
            return {"visible": visible, "__type__": "update"}

        def story_options(x):
            if x in STORIES:
                return [
                    gr.Dropdown.update(choices=STORIES[x]["poses"], label=f"Pose (for {x})"),
                    gr.Dropdown.update(choices=STORIES[x]["pages"], label=f"Page (for {x})")
                ]
            return [
                gr.Dropdown.update(choices=[], label="Unknown Poses"),
                gr.Dropdown.update(choices=[], label="Unknown Pages")
            ]

        # Checkbox to save image and show options
        checkbox_save_to_gs = gr.inputs.Checkbox(label="Save to Image Collector", default=False)

        # Group the options for saving and only show them when the checkbox is checked
        with FormGroup(visible=False, elem_id="save_to_image_uploader") as hr_options:
            with gr.Row():
                with gr.Column(scale=1):
                    character = gr.inputs.Dropdown(CHARACTERS, label="Character Name")
                with gr.Column(scale=4):
                    story = gr.inputs.Dropdown(list(STORIES.keys()), label="Story Name")
                    page = gr.inputs.Dropdown(["1", "2", "3"], label="Page Number")
                    pose = gr.inputs.Dropdown(["Running", "Sitting Looking Up"], label="Pose")
            with gr.Row():
                notes = gr.inputs.Textbox(
                    label="Image Notes",
                    default="",
                    placeholder="Provide Image Notes to Save (Optional)"
                )

        story.change(fn=story_options, inputs=story, outputs=[pose, page], show_progress=True, status_tracker=None)

        checkbox_save_to_gs.change(
            fn=lambda x: gr_show(x),
            inputs=[checkbox_save_to_gs],
            outputs=[hr_options],
            show_progress=False,
        )

        return [
            checkbox_save_to_gs,
            story,
            character,
            page,
            pose,
            notes,
        ]

    def postprocess(self, p, processed, checkbox_save_to_gs, story, character, page, pose, notes):
        print('postprocess')
        global generated_images

        # Name the process so that it can be found in the history
        process_name = p.__class__.__name__.replace("StableDiffusion", "")
        # Reset Images if the process is txt2img
        if process_name == "ProcessingTxt2Img":
            print("Resetting Generating Images Collection")
            generated_images = []

        # Normalize the book info
        story = story if story else "Unknown Story"
        character = character if character else "Unknown Character"
        page = page if page else "Unknown Page"
        pose = pose if pose else "Unknown Pose"
        notes = notes if notes else ""

        # Add generation meta data
        generation_meta = get_generation_info(processed)

        for i in range(len(processed.images)):
            image = processed.images[i]
            is_grid_sized = image.width != processed.width or image.height != processed.height
            if is_grid_sized:
                print(f"Skipping image {i} because it is grid sized")
                continue
            # Add metadata to image such that the save action can access
            processed.images[i].info['story'] = story
            processed.images[i].info['character'] = character
            processed.images[i].info['page'] = page
            processed.images[i].info['pose'] = pose
            processed.images[i].info['notes'] = notes
            processed.images[i].info['process_name'] = process_name
            # Add generation meta data
            for k, v in generation_meta.items():
                processed.images[i].info[k] = v
            generated_images.append(processed.images[i])

        return True


def on_ui_settings():
    section = ('kiras-image-submitter', "Kira's Image Submitter")
    opts.add_option(
        "kira_image_submitter_service_url",
        OptionInfo('', "Service URL", section=section)
    )
    opts.add_option(
        "kira_image_submitter_service_api_key",
        OptionInfo('', "Service API Key", section=section)
    )


script_callbacks.on_ui_settings(on_ui_settings)
