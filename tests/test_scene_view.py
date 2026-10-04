import numpy as np

from nicegui import ui
from nicegui.testing import Screen


def test_create_dynamically(screen: Screen):
    scene = scene_view = None

    @ui.page('/')
    def page():
        nonlocal scene
        scene = ui.scene()

        def create():
            nonlocal scene_view
            scene_view = ui.scene_view(scene)
        ui.button('Create', on_click=create)

    screen.open('/')
    screen.click('Create')
    screen.wait(0.5)
    assert scene_view is not None
    assert screen.selenium.execute_script(f'return getElement({scene_view.id}).scene == getElement({scene.id}).scene')


def test_object_creation_via_context(screen: Screen):
    scene = scene_view = None

    @ui.page('/')
    def page():
        nonlocal scene, scene_view
        with ui.scene() as scene:
            scene.box()

        scene_view = ui.scene_view(scene)

    screen.open('/')
    screen.wait(1)
    assert screen.selenium.execute_script(f'return getElement({scene_view.id}).scene == getElement({scene.id}).scene')


def test_camera_move(screen: Screen):
    scene = scene_view = None

    @ui.page('/')
    def page():
        nonlocal scene, scene_view
        with ui.scene() as scene:
            scene.box()

        scene_view = ui.scene_view(scene)

    screen.open('/')

    screen.wait(0.5)
    scene_view.move_camera(x=1, y=2, z=3, look_at_x=4, look_at_y=5, look_at_z=6, up_x=7, up_y=8, up_z=9, duration=0.0)

    screen.wait(1)
    position = screen.selenium.execute_script(f'return getElement({scene_view.id}).camera_tween._object')
    assert np.allclose(position, [1, 2, 3, 7, 8, 9, 4, 5, 6])


def test_view_redraws_when_an_on_demand_scene_changes(screen: Screen):
    scene_view = None
    box = None

    @ui.page('/')
    def page():
        nonlocal scene_view, box
        with ui.scene(render_on_demand=True) as scene:
            box = scene.box()
        scene_view = ui.scene_view(scene)

    screen.open('/')
    frames = f'return getElement({scene_view.id}).renderer.info.render.frame'
    screen.wait(0.5)
    drawn = screen.selenium.execute_script(frames)
    screen.wait(0.5)
    assert screen.selenium.execute_script(frames) == drawn, 'an unchanged scene is not redrawn in its view'

    box.move(1, 0, 0)
    screen.wait(0.5)
    assert screen.selenium.execute_script(frames) > drawn, 'a moved object is drawn in the view'
