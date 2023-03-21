from io import BytesIO
import re

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


class Scripts(scripts.Script):
    def title(self):
        return "Save to Image Collector"

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
        with FormGroup(visible=False, elem_id="txt2img_hires_fix") as hr_options:
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
        if not checkbox_save_to_gs:
            print("Not saving to GCS")
            return True

        # Normalize the book info
        story = story if story else "Unknown Story"
        character = character if character else "Unknown Character"
        page = page if page else "Unknown Page"
        pose = pose if pose else "Unknown Pose"

        print("Going to save image")
        for i in range(len(processed.images)):
            # Capture Image and upload to GCS
            image = processed.images[i]

            # Add metadata to image
            pnginfo_data = PngImagePlugin.PngInfo()
            for k, v in image.info.items():
                pnginfo_data.add_text(k, str(v))

            # Add Book metadata
            pnginfo_data.add_text("story", story)
            pnginfo_data.add_text("character", character)
            pnginfo_data.add_text("page", page)
            pnginfo_data.add_text("pose", pose)
            pnginfo_data.add_text("notes", notes)

            # Add Additional Metadata
            generation_info = get_generation_info(processed)
            for k, v in generation_info.items():
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
            signed_url = get_signed_url_for_prompt_image(
                image_path,
                service_url,
                api_key
            )
            print(f"Signed URL: {signed_url}")
            upload_image_to_gs(image_bytes, signed_url)
            print(f"File Uploaded to {image_path}")
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
