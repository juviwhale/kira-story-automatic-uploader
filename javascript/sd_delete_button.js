function txt2img_kira_uploader_hide() {
    const txt2img_kira_uploader_status_info = gradioApp().getElementById('txt2img_kira_uploader_status_info')
    txt2img_kira_uploader_status_info.style.display = 'none'
}

function img2img_kira_uploader_hide() {
    const img2img_kira_uploader_status_info = gradioApp().getElementById('img2img_kira_uploader_status_info')
    img2img_kira_uploader_status_info.style.display = 'none'
}

function txt2img_kira_uploader_addEventListener() {
    const txt2img_generate = gradioApp().getElementById('txt2img_generate')
    txt2img_generate.removeEventListener('click', txt2img_kira_uploader_hide)
    txt2img_generate.addEventListener('click', txt2img_kira_uploader_hide)
    const txt2img_kira_uploader_status_info = gradioApp().getElementById('txt2img_kira_uploader_status_info')
    txt2img_kira_uploader_status_info.style.display = ''
}

function img2img_kira_uploader_addEventListener() {
    const img2img_generate = gradioApp().getElementById('img2img_generate')
    img2img_generate.removeEventListener('click', img2img_kira_uploader_hide)
    img2img_generate.addEventListener('click', img2img_kira_uploader_hide)
    const img2img_kira_uploader_status_info = gradioApp().getElementById('img2img_kira_uploader_status_info')
    img2img_kira_uploader_status_info.style.display = ''
}