from typing_extensions import Self

from ..scene_object3d import Object3D


class Text(Object3D, component='text.js'):
    def __init__(self, text: str, style: str = '') -> None:
        """Text

        This element is used to add 2D text to the scene.
        It can be moved like any other object, but always faces the camera.

        :param text: text to display
        :param style: CSS style (default: '')
        """
        super().__init__(text, style)

    def set_text(self, text: str) -> Self:
        """Change the displayed text.

        *Added in version 3.18.0*
        """
        self.args[0] = text
        self.run_method('set_text', text)
        return self

    def set_style(self, style: str) -> Self:
        """Change the CSS style.

        *Added in version 3.18.0*
        """
        self.args[1] = style
        self.run_method('set_style', style)
        return self
