import { CSS3DObject } from "nicegui-scene";

export default class Text3D {
  div;

  create_mesh(text, style) {
    this.div = document.createElement("div");
    this.set_text(text);
    this.set_style(style);
    return new CSS3DObject(this.div);
  }
  set_text(text) {
    this.div.textContent = text;
  }
  set_style(style) {
    this.div.style.cssText = "user-select:none;" + style;
  }
}
