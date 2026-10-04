import gc
import weakref
from typing import Literal

import numpy as np
import pytest
from selenium.common.exceptions import JavascriptException
from selenium.webdriver import ActionChains
from selenium.webdriver.common.actions.action_builder import ActionBuilder

from nicegui import app, ui
from nicegui.elements.scene import Object3D
from nicegui.events import GenericEventArguments
from nicegui.testing import Screen, User

from .test_helpers import TEST_DIR


def test_moving_sphere_with_timer(screen: Screen):
    scene = None

    @ui.page('/')
    def page():
        nonlocal scene
        with ui.scene() as scene:
            sphere = scene.sphere().with_name('sphere')
            ui.timer(0.1, lambda: sphere.move(0, 0, sphere.z + 0.01))

    screen.open('/')

    def position() -> float:
        for _ in range(3):
            try:
                pos = screen.selenium.execute_script(
                    f'return scene_{scene.html_id}.getObjectByName("sphere").position.z')
                if pos is not None:
                    return pos
            except JavascriptException as e:
                print(e.msg, flush=True)
            screen.wait(1.0)
        raise RuntimeError('Could not get position')

    screen.wait(0.2)
    assert position() > 0


def test_no_object_duplication_on_index_client(screen: Screen):
    scene = None

    @ui.page('/')
    def page():
        nonlocal scene
        with ui.scene() as scene:
            sphere = scene.sphere().move(0, -4, 0)
            ui.timer(0.1, lambda: sphere.move(0, sphere.y + 0.5, 0))

    screen.open('/')
    screen.wait(0.4)
    screen.switch_to(1)
    screen.open('/')
    screen.switch_to(0)
    screen.wait(0.2)
    assert screen.selenium.execute_script(f'return scene_{scene.html_id}.children.length') == 5


def test_no_object_duplication_with_page_builder(screen: Screen):
    scene_html_ids: list[int] = []

    @ui.page('/')
    def page():
        with ui.scene() as scene:
            sphere = scene.sphere().move(0, -4, 0)
            ui.timer(0.1, lambda: sphere.move(0, sphere.y + 0.5, 0))
        scene_html_ids.append(scene.html_id)

    screen.open('/')
    screen.wait(0.4)
    screen.switch_to(1)
    screen.open('/')
    screen.switch_to(0)
    screen.wait(0.2)
    assert screen.selenium.execute_script(f'return scene_{scene_html_ids[0]}.children.length') == 5
    screen.switch_to(1)
    screen.wait(0.2)
    assert screen.selenium.execute_script(f'return scene_{scene_html_ids[1]}.children.length') == 5


def test_deleting_group(screen: Screen):
    scene = None

    @ui.page('/')
    def page():
        nonlocal scene
        with ui.scene() as scene:
            with scene.group() as group:
                scene.sphere()
        ui.button('Delete group', on_click=group.delete)

    screen.open('/')
    screen.wait(0.5)
    assert len(scene.objects) == 2
    screen.click('Delete group')
    screen.wait(0.5)
    assert len(scene.objects) == 0


def test_deleting_object_right_after_creation(screen: Screen):
    scene = None

    @ui.page('/')
    def page():
        nonlocal scene
        with ui.scene() as scene:
            scene.box().with_name('warmup')  # when the button is clicked, box.js is already loaded but group.js is not

        def create_and_delete():
            with scene, scene.group().with_name('group'):
                scene.box().with_name('box').delete()

        ui.button('Create and delete', on_click=create_and_delete)

    screen.open('/')
    screen.wait_for_js(f'scene_{scene.html_id}.getObjectByName("warmup")?.type', 'Mesh')
    screen.click('Create and delete')
    screen.wait_for_js(f'scene_{scene.html_id}.getObjectByName("group")?.type', 'Group')
    assert screen.selenium.execute_script(f'return scene_{scene.html_id}.getObjectByName("box")?.type ?? null') is None


def test_moving_right_after_detaching(screen: Screen):
    scene = None

    @ui.page('/')
    def page():
        nonlocal scene
        scene = ui.scene()

        def detach_and_move():
            with scene, scene.group():
                box = scene.box().with_name('box')
            box.detach()
            box.move(1, 2, 3)

        ui.button('Detach and move', on_click=detach_and_move)

    screen.open('/')
    screen.click('Detach and move')
    screen.wait_for_js(f'scene_{scene.html_id}.getObjectByName("box")?.parent?.type', 'Scene')
    screen.wait_for_js(f'scene_{scene.html_id}.getObjectByName("box")?.position.x', 1)


def test_replace_scene(screen: Screen):
    scene = None

    @ui.page('/')
    def page():
        nonlocal scene
        with ui.row() as container:
            with ui.scene() as scene:
                scene.sphere().with_name('sphere')

        def replace():
            with container.clear():
                nonlocal scene
                with ui.scene() as scene:
                    scene.box().with_name('box')
        ui.button('Replace scene', on_click=replace)

    screen.open('/')
    screen.wait(0.5)
    assert screen.selenium.execute_script(f'return scene_{scene.html_id}.children[4].name') == 'sphere'

    screen.click('Replace scene')
    screen.wait(0.5)
    assert screen.selenium.execute_script(f'return scene_{scene.html_id}.children[4].name') == 'box'


def test_create_dynamically(screen: Screen):
    @ui.page('/')
    def page():
        ui.button('Create', on_click=ui.scene)

    screen.open('/')
    screen.click('Create')
    assert screen.find_by_tag('canvas')


def test_rotation_matrix_from_euler():
    omega, phi, kappa = 0.1, 0.2, 0.3
    Rx = np.array([[1, 0, 0], [0, np.cos(omega), -np.sin(omega)], [0, np.sin(omega), np.cos(omega)]])
    Ry = np.array([[np.cos(phi), 0, np.sin(phi)], [0, 1, 0], [-np.sin(phi), 0, np.cos(phi)]])
    Rz = np.array([[np.cos(kappa), -np.sin(kappa), 0], [np.sin(kappa), np.cos(kappa), 0], [0, 0, 1]])
    R = Rz @ Ry @ Rx
    assert np.allclose(Object3D.rotation_matrix_from_euler(omega, phi, kappa), R)


def test_object_creation_via_context(screen: Screen):
    scene = None

    @ui.page('/')
    def page():
        nonlocal scene
        with ui.scene() as scene:
            scene.box().with_name('box')

    screen.open('/')
    screen.wait(0.5)
    assert screen.selenium.execute_script(f'return scene_{scene.html_id}.children[4].name') == 'box'


def test_object_creation_via_attribute(screen: Screen):
    scene = None

    @ui.page('/')
    def page():
        nonlocal scene
        scene = ui.scene()
        scene.box().with_name('box')

    screen.open('/')
    screen.wait(0.5)
    assert screen.selenium.execute_script(f'return scene_{scene.html_id}.children[4].name') == 'box'


def test_clearing_scene(screen: Screen):
    scene = None

    @ui.page('/')
    def page():
        nonlocal scene
        with ui.scene() as scene:
            scene.box().with_name('box')
            with scene.group():  # see https://github.com/zauberzeug/nicegui/issues/4560
                scene.box().with_name('box2')
        ui.button('Clear', on_click=scene.clear)

    screen.open('/')
    screen.wait(0.5)
    assert len(scene.objects) == 3
    screen.click('Clear')
    screen.wait(0.5)
    assert len(scene.objects) == 0


@pytest.mark.parametrize('set_material, color', [
    (False, 'e70000'),  # without material(), box.glb keeps its own red material (baseColorFactor 0.8 -> "e70000")
    (True, 'ff0000'),  # explicit material() overrides the model's own material
])
def test_gltf(screen: Screen, set_material: bool, color: str):
    scene = None

    @ui.page('/')
    def page():
        nonlocal scene
        app.add_static_file(local_file=TEST_DIR / 'media' / 'box.glb', url_path='/box.glb')
        with ui.scene() as scene:
            gltf = scene.gltf('/box.glb')
            if set_material:
                gltf.material(f'#{color}')

    screen.open('/')
    screen.wait(1.0)
    assert screen.selenium.execute_script(f'return scene_{scene.html_id}.children.length') == 5
    assert screen.selenium.execute_script(
        f'return scene_{scene.html_id}.children[4].getObjectByProperty("isMesh", true).material.color.getHexString()'
    ) == color


def test_stl_wireframe(screen: Screen):
    """A wireframe STL must render as edges (a LineSegments with EdgesGeometry), be colorable, and follow renames."""
    scene = None
    obj = None

    @ui.page('/')
    def page():
        nonlocal scene, obj
        app.add_static_file(local_file=TEST_DIR / 'media' / 'cube.stl', url_path='/cube.stl')
        with ui.scene() as scene:
            obj = scene.stl('/cube.stl', wireframe=True).material('#ff0000')
        ui.button('Rename', on_click=lambda: obj.with_name('renamed'))

    screen.open('/')
    screen.wait_for_js(f'scene_{scene.html_id}.getObjectByProperty("object_id", "{obj.id}")?.children.length > 0', True)
    result = screen.selenium.execute_script(f'''
        const group = scene_{scene.html_id}.getObjectByProperty("object_id", "{obj.id}");
        const child = group.children[0];
        return {{
            root_type: group.type,
            child_geometry: child ? child.geometry.type : null,
            edge_count: (child && child.geometry.attributes.position) ? child.geometry.attributes.position.count : 0,
            child_color: (child && child.material) ? child.material.color.getHexString() : null,
        }};
    ''')
    assert result['root_type'] == 'Group', f'expected a Group wrapper, got {result}'
    assert result['child_geometry'] == 'EdgesGeometry', f'expected EdgesGeometry child, got {result}'
    assert result['edge_count'] > 0, f'expected non-empty edges, got {result}'
    assert result['child_color'] == 'ff0000', f'expected material to reach the wireframe lines, got {result}'

    screen.click('Rename')  # rename AFTER the async load has completed
    screen.wait_for_js(f'scene_{scene.html_id}.getObjectByProperty("object_id", "{obj.id}").name', 'renamed')


def test_no_cyclic_references(screen: Screen):
    objects: weakref.WeakSet = weakref.WeakSet()
    scene = None

    @ui.page('/')
    def page():
        nonlocal scene
        with ui.scene() as scene:
            for _ in range(10):
                objects.add(scene.box())

        ui.button('Clear', on_click=scene.clear)

    screen.open('/')
    screen.click('Clear')
    assert len(objects) == 0


@pytest.mark.parametrize('control_type,constructor', [('map', 'MapControls'), ('trackball', 'TrackballControls')])
def test_custom_controls(screen: Screen, control_type: Literal['map', 'trackball'], constructor: str):
    scene = None

    @ui.page('/')
    def page():
        nonlocal scene
        scene = ui.scene(control_type=control_type)

    screen.open('/')
    screen.wait_for(lambda: scene is not None)
    assert screen.selenium.execute_script(f'return getElement({scene.id}).controls.constructor.name') == constructor


def test_transform_controls_enable_disable(screen: Screen):
    scene = None
    box = None

    @ui.page('/')
    def page():
        nonlocal scene, box
        with ui.scene() as scene:
            box = scene.box()
        ui.button('Enable', on_click=lambda: box.enable_transform_controls(mode='translate'))
        ui.button('Disable', on_click=box.disable_transform_controls)

    screen.open('/')
    screen.wait_for(lambda: screen.selenium.execute_script(
        f'const el = getElement({scene.id}); return el && !!el.renderer'
    ))
    screen.click('Enable')
    screen.wait_for(lambda: screen.selenium.execute_script(
        f'return getElement({scene.id}).has_transform_controls("{box.id}")'
    ))
    screen.click('Disable')
    screen.wait_for(lambda: not screen.selenium.execute_script(
        f'return getElement({scene.id}).has_transform_controls("{box.id}")'
    ))


def test_transform_controls_mode_change(screen: Screen):
    scene = None
    box = None

    @ui.page('/')
    def page():
        nonlocal scene, box
        with ui.scene() as scene:
            box = scene.box()
        ui.button('Translate', on_click=lambda: box.enable_transform_controls(mode='translate'))
        ui.button('Rotate', on_click=lambda: box.set_transform_mode('rotate'))
        ui.button('Scale', on_click=lambda: box.set_transform_mode('scale'))

    screen.open('/')
    screen.wait_for(lambda: screen.selenium.execute_script(
        f'const el = getElement({scene.id}); return el && !!el.renderer'
    ))
    screen.click('Translate')
    screen.wait_for(lambda: screen.selenium.execute_script(
        f'return getElement({scene.id}).transform_controls.get("{box.id}")?.mode === "translate"'
    ))
    screen.click('Rotate')
    screen.wait_for(lambda: screen.selenium.execute_script(
        f'return getElement({scene.id}).transform_controls.get("{box.id}")?.mode === "rotate"'
    ))
    screen.click('Scale')
    screen.wait_for(lambda: screen.selenium.execute_script(
        f'return getElement({scene.id}).transform_controls.get("{box.id}")?.mode === "scale"'
    ))


def _viewport_point(screen: Screen, scene: ui.scene, x: float, y: float, z: float) -> tuple[int, int]:
    return screen.selenium.execute_script(
        f'const el = getElement({scene.id});'
        f'const p = el.camera.position.clone().set({x}, {y}, {z}).project(el.camera);'
        'const r = el.renderer.domElement.getBoundingClientRect();'
        'return [Math.round(r.left + (p.x + 1) / 2 * r.width), Math.round(r.top + (1 - p.y) / 2 * r.height)];'
    )


def _move_pointer(screen: Screen, x: int, y: int) -> None:
    actions = ActionBuilder(screen.selenium)
    actions.pointer_action.move_to_location(x, y)
    actions.perform()


def _drag(screen: Screen, x: int, y: int, dx: int, dy: int) -> None:
    actions = ActionBuilder(screen.selenium)
    actions.pointer_action.move_to_location(x, y).pointer_down() \
        .move_to_location(x + dx // 2, y + dy // 2).move_to_location(x + dx, y + dy).pointer_up()
    actions.perform()


def test_disabled_orbit_survives_a_gizmo_drag(screen: Screen):
    ends: list[float] = []
    scene = None
    box = None

    @ui.page('/')
    def page():
        nonlocal scene, box
        with ui.scene(on_transform_end=lambda e: ends.append(e.x)) as scene:
            box = scene.box()
        box.enable_transform_controls()

    screen.open('/')
    screen.wait_for_js(f'getElement({scene.id}).has_transform_controls("{box.id}")', True)
    scene.set_orbit_enabled(False)
    screen.wait_for_js(f'getElement({scene.id}).controls.enabled', False)
    x, y = _viewport_point(screen, scene, 1, 0, 0)  # on the X arrow, past the box
    _drag(screen, x, y, 60, 0)
    screen.wait_for(lambda: ends)

    camera = f'getElement({scene.id}).camera.position.toArray()'
    before = screen.selenium.execute_script(f'return {camera}')
    x, y = _viewport_point(screen, scene, -2, 1, 0)
    _drag(screen, x, y, 80, 40)
    assert screen.selenium.execute_script(f'return {camera}') == pytest.approx(before), 'orbiting must stay disabled'


def test_interactive_state_survives_context_loss(screen: Screen):
    overs: list[str] = []
    scene = None
    box = None

    @ui.page('/')
    def page():
        nonlocal scene, box
        with ui.scene() as scene:
            box = scene.box().on_pointer_over(lambda e: overs.append(e.object_id)).hover_effect('glow')

    screen.open('/')
    screen.wait_for_js(f'getElement({scene.id}).has_effect("{box.id}")', True)
    screen.selenium.execute_script(
        'document.querySelector("canvas").getContext("webgl2").getExtension("WEBGL_lose_context").loseContext();'
    )
    screen.click('Click to re-initialize')
    screen.wait_for_js(f'getElement({scene.id})?.has_effect?.("{box.id}") ?? false', True)

    _move_pointer(screen, *_viewport_point(screen, scene, 0, 0, 0.5))
    screen.wait_for(lambda: overs == [box.id])
    glow = f'scene_{scene.html_id}.children.some(c => c.isGroup && c.children.some(m => m.material?.side === 1))'
    screen.wait_for_js(glow, True)


def test_hover_effects(screen: Screen):
    scene = None
    box = None

    @ui.page('/')
    def page():
        nonlocal scene, box
        with ui.scene() as scene:
            box = scene.box()

    screen.open('/')
    # what a hover adds: a back-face glow mesh, outline edges, and the box's emissive tint
    shown = (
        '(() => {'
        f'  const added = scene_{scene.html_id}.children.filter(c => c.isGroup).flatMap(g => g.children);'
        f'  const tint = getElement({scene.id}).objects.get("{box.id}").mesh.material.emissive.getHexString();'
        '  return [added.some(m => m.isMesh && m.material.side === 1), added.some(m => m.isLineSegments), tint];'
        '})()'
    )
    on_box = _viewport_point(screen, scene, 0, 0, 0.5)
    off_box = _viewport_point(screen, scene, -2, 0, 0)
    for effect, hovered in [('glow', [True, False, '000000']),
                            ('outline', [False, True, '000000']),
                            ('tint', [False, False, 'ffffff'])]:
        box.hover_effect(effect)
        screen.wait_for_js(f'getElement({scene.id}).objectEffects.get("{box.id}")?.effect', effect)
        _move_pointer(screen, *on_box)
        screen.wait_for_js(shown, hovered)
        _move_pointer(screen, *off_box)
        screen.wait_for_js(shown, [False, False, '000000'])


def test_pointer_events_of_an_object(screen: Screen):
    events: list[str] = []
    scene = None
    box = None

    @ui.page('/')
    def page():
        nonlocal scene, box
        with ui.scene(on_pointer_missed=lambda e: events.append(f'missed {e.type}')) as scene:
            box = scene.box()
        for register in (box.on_pointer_over, box.on_pointer_out, box.on_click, box.on_double_click,
                         box.on_context_menu):
            register(lambda e: events.append(e.type if e.object_id == box.id else 'another object'))

    screen.open('/')
    screen.wait_for_js(f'getElement({scene.id}).has_handler("{box.id}", "contextmenu")', True)
    x, y = _viewport_point(screen, scene, 0, 0, 0.5)
    actions = ActionBuilder(screen.selenium)
    actions.pointer_action.move_to_location(x, y).double_click().context_click()
    actions.perform()
    x, y = _viewport_point(screen, scene, -2, 0, 0)
    actions = ActionBuilder(screen.selenium)
    actions.pointer_action.move_to_location(x, y).click()
    actions.perform()
    screen.wait_for(lambda: 'missed click' in events)
    assert events == ['pointerover', 'click', 'click', 'dblclick', 'contextmenu', 'pointerout',
                      'missed pointerdown', 'missed click']


def test_dragging_transform_controls(screen: Screen):
    ends: list[tuple[float, float]] = []
    misses: list[str] = []
    scene = None
    box = None

    @ui.page('/')
    def page():
        nonlocal scene, box
        with ui.scene(on_transform_end=lambda e: ends.append((e.x, box.x)),
                      on_pointer_missed=lambda e: misses.append(e.type)) as scene:
            box = scene.box().on_click(lambda _: None)
        box.enable_transform_controls()

    screen.open('/')
    screen.wait_for_js(f'getElement({scene.id}).has_transform_controls("{box.id}")', True)
    _drag(screen, *_viewport_point(screen, scene, 1, 0, 0), 60, 0)  # by the X arrow, past the box
    screen.wait_for(lambda: ends)
    reported_x, object_x = ends[0]
    assert reported_x > 0
    assert object_x == reported_x

    x, y = _viewport_point(screen, scene, -2, 0, 0)
    actions = ActionBuilder(screen.selenium)
    actions.pointer_action.move_to_location(x, y).click()
    actions.perform()
    screen.wait_for(lambda: 'click' in misses)
    assert misses == ['pointerdown', 'click'], 'grabbing the gizmo is not a miss, only the click into empty space is'


def test_clicking_an_object_with_transform_controls(screen: Screen):
    hits: list[list[str]] = []
    scene = None
    box = None

    @ui.page('/')
    def page():
        nonlocal scene, box
        with ui.scene(on_click=lambda e: hits.append([hit.object_id for hit in e.hits])) as scene:
            box = scene.box()
        box.enable_transform_controls()

    screen.open('/')
    screen.wait_for_js(f'getElement({scene.id}).has_transform_controls("{box.id}")', True)
    x, y = _viewport_point(screen, scene, 0.3, 0.3, 0.5)
    actions = ActionBuilder(screen.selenium)
    actions.pointer_action.move_to_location(x, y).click()
    actions.perform()
    screen.wait_for(lambda: hits)
    assert hits == [[box.id, 'ground']]


def test_changing_the_material_of_a_tinted_object(screen: Screen):
    scene = None
    box = None

    @ui.page('/')
    def page():
        nonlocal scene, box
        with ui.scene() as scene:
            box = scene.box().hover_effect('tint').on_click(lambda _: box.material('#ff0000'))

    screen.open('/')
    screen.wait_for_js(f'getElement({scene.id}).has_effect("{box.id}")', True)
    material = f'getElement({scene.id}).objects.get("{box.id}").mesh.material'
    x, y = _viewport_point(screen, scene, 0, 0, 0.5)
    actions = ActionBuilder(screen.selenium)
    actions.pointer_action.move_to_location(x, y).click()
    actions.perform()
    screen.wait_for_js(f'{material}.color.getHexString()', 'ff0000')

    _move_pointer(screen, *_viewport_point(screen, scene, -2, 0, 0))
    screen.wait_for_js(f'{material}.emissive.getHexString()', '000000')  # the tint is gone
    assert screen.selenium.execute_script(f'return {material}.color.getHexString()') == 'ff0000'


def test_glow_of_an_object_at_the_origin(screen: Screen):
    scene = None
    box = None

    @ui.page('/')
    def page():
        nonlocal scene, box
        with ui.scene(hover_scale=1.2) as scene:
            box = scene.box().hover_effect('glow')

    screen.open('/')
    screen.wait_for_js(f'getElement({scene.id}).has_effect("{box.id}")', True)
    _move_pointer(screen, *_viewport_point(screen, scene, 0, 0, 0.5))
    glow = f'scene_{scene.html_id}.children.flatMap(c => c.children).find(m => m.material?.side === 1)'
    screen.wait_for_js(f'{glow}?.scale.toArray() ?? null', [1.2, 1.2, 1.2])


def test_moving_camera_keeps_controls_unless_up_vector_changes(screen: Screen):
    scene = None

    @ui.page('/')
    def page():
        nonlocal scene
        scene = ui.scene()

    screen.open('/')
    screen.wait_for(lambda: scene is not None)
    enable_rotate = f'getElement({scene.id}).controls.enableRotate'
    screen.selenium.execute_script(f'{enable_rotate} = false')

    camera_x = f'getElement({scene.id}).camera.position.x'
    scene.move_camera(x=1, duration=0)
    screen.wait_for(lambda: screen.selenium.execute_script(f'return {camera_x}') == pytest.approx(1))
    assert screen.selenium.execute_script(f'return {enable_rotate}') is False, 'controls survive a plain camera move'

    camera_up_y = f'getElement({scene.id}).camera.up.y'
    scene.move_camera(up_y=1, up_z=0, duration=0)
    screen.wait_for(lambda: screen.selenium.execute_script(f'return {camera_up_y}') == pytest.approx(1))
    assert screen.selenium.execute_script(f'return {enable_rotate}') is True, 'controls are rebuilt for a new up vector'


def test_moving_camera_keeps_trackball_controls_after_rotating(screen: Screen):
    scene = None

    @ui.page('/')
    def page():
        nonlocal scene
        scene = ui.scene(control_type='trackball')

    screen.open('/')
    screen.wait_for(lambda: scene is not None)
    static_moving = f'getElement({scene.id}).controls.staticMoving'
    screen.selenium.execute_script(f'{static_moving} = true')  # no rotation momentum after releasing the mouse

    canvas = screen.find_by_tag('canvas')
    screen.wait_for(canvas.is_displayed)  # the scene is hidden until it is initialized
    ActionChains(screen.selenium).click_and_hold(canvas).move_by_offset(50, 50).release().perform()
    camera_up_z = f'getElement({scene.id}).camera.up.z'
    screen.wait_for(lambda: screen.selenium.execute_script(f'return {camera_up_z}') != 1)  # the user rotated the scene

    camera_x = f'getElement({scene.id}).camera.position.x'
    scene.move_camera(x=1, duration=0)
    screen.wait_for(lambda: screen.selenium.execute_script(f'return {camera_x}') == pytest.approx(1))
    assert screen.selenium.execute_script(f'return {static_moving}') is True


def test_trackball_controls_follow_canvas_size(screen: Screen):
    scene = None

    @ui.page('/')
    def page():
        nonlocal scene
        scene = ui.scene(control_type='trackball').classes('w-full h-64')

    screen.open('/')
    canvas = screen.find_by_tag('canvas')
    screen.wait_for(canvas.is_displayed)  # the scene is hidden until it is initialized
    assert canvas.size['width'] != 400, 'the canvas has been resized from its default size'
    screen_width = f'getElement({scene.id}).controls.screen.width'
    assert screen.selenium.execute_script(f'return {screen_width}') == canvas.size['width']


def test_configuring_controls_after_initialization(screen: Screen):
    scene = None

    @ui.page('/')
    async def page():
        nonlocal scene
        scene = ui.scene()
        scene.move_camera(up_y=1, up_z=0)
        await scene.initialized()
        ui.run_javascript(f'getElement({scene.id}).controls.enableRotate = false')

    screen.open('/')
    camera_up_y = f'getElement({scene.id}).camera.up.y'
    screen.wait_for(lambda: screen.selenium.execute_script(f'return {camera_up_y}') == pytest.approx(1))
    enable_rotate = f'getElement({scene.id}).controls.enableRotate'
    assert screen.selenium.execute_script(f'return {enable_rotate}') is False, 'configuration survives initialization'


async def test_dragend_after_object_deleted(user: User):
    events: list[str] = []
    scene = None
    box = None

    @ui.page('/')
    def page():
        nonlocal scene, box
        with ui.scene(on_drag_end=lambda e: events.append(e.object_id)) as scene:
            box = scene.box().draggable()

    await user.open('/')
    box.delete()
    assert box.id not in scene.objects
    scene._handle_drag(GenericEventArguments(sender=scene, client=scene.client, args={
        'type': 'dragend', 'object_id': box.id, 'object_name': None, 'x': 1.0, 'y': 2.0, 'z': 3.0,
    }))
    assert events == [box.id]


async def test_bound_object_is_released_on_delete(user: User):
    objects: weakref.WeakSet = weakref.WeakSet()

    @ui.page('/')
    def page():
        scene = ui.scene()
        label = ui.label()
        box = scene.box()
        objects.add(box)
        label.bind_text_from(box, 'x')
        box.delete()

    await user.open('/')
    gc.collect()
    assert len(objects) == 0


async def test_scene_is_collected_after_client_deletion(user: User):
    held = []  # stands in for a timer or handler holding the scene
    objects: weakref.WeakSet = weakref.WeakSet()

    @ui.page('/')
    def page():
        scene = ui.scene()
        held.append(scene)
        objects.add(scene)

    await user.open('/')
    user.client.delete()
    objects.add(held[0].box())  # late access after the client is gone
    held.clear()  # the timer finishes and drops its reference
    gc.collect()
    assert len(objects) == 0


def test_context_loss_recovery_restores_objects(screen: Screen):
    scene = None

    @ui.page('/')
    def page():
        nonlocal scene
        with ui.scene() as scene:
            scene.box().material('#ff0000').move(1, 2, 3).with_name('box')

    screen.open('/')
    screen.wait_for_js(f'scene_{scene.html_id}.getObjectByName("box")?.position.x ?? null', 1)
    screen.selenium.execute_script(f'''
        window.sceneBeforeRecovery = scene_{scene.html_id};
        document.querySelector("canvas").getContext("webgl2").getExtension("WEBGL_lose_context").loseContext();
    ''')
    screen.click('Click to re-initialize')
    screen.wait_for_js(f'scene_{scene.html_id} !== window.sceneBeforeRecovery', True)  # remounting replaces the scene
    screen.wait_for_js(f'scene_{scene.html_id}.getObjectByName("box")?.position.x ?? null', 1)
    screen.wait_for_js(f'scene_{scene.html_id}.getObjectByName("box").material.color.getHexString()', 'ff0000')


def test_clicking_the_grid_reports_only_the_ground(screen: Screen):
    hits: list[str] = []

    @ui.page('/')
    def page():
        ui.scene(on_click=lambda e: hits.extend(hit.object_id for hit in e.hits))

    screen.open('/')
    screen.find_by_tag('canvas').click()
    screen.wait_for(lambda: hits == ['ground'])


def test_rotation_matrix_from_euler_all_orders():
    rx, ry, rz = 0.4, -0.3, 0.5
    Rx = np.array([[1, 0, 0], [0, np.cos(rx), -np.sin(rx)], [0, np.sin(rx), np.cos(rx)]])
    Ry = np.array([[np.cos(ry), 0, np.sin(ry)], [0, 1, 0], [-np.sin(ry), 0, np.cos(ry)]])
    Rz = np.array([[np.cos(rz), -np.sin(rz), 0], [np.sin(rz), np.cos(rz), 0], [0, 0, 1]])
    axis = {'X': Rx, 'Y': Ry, 'Z': Rz}
    # Leftmost letter rotates first about the world frame, so the leftmost axis sits as the
    # rightmost matrix in the product (column-vector convention M @ v).
    expected_per_order = {
        'XYZ': Rz @ Ry @ Rx,
        'XZY': Ry @ Rz @ Rx,
        'YXZ': Rz @ Rx @ Ry,
        'YZX': Rx @ Rz @ Ry,
        'ZXY': Ry @ Rx @ Rz,
        'ZYX': Rx @ Ry @ Rz,
    }
    assert set(expected_per_order) == set(Object3D.EULER_ORDERS)
    for order, expected in expected_per_order.items():
        actual = Object3D.rotation_matrix_from_euler(rx, ry, rz, order)
        assert np.allclose(actual, expected), f'{order} mismatch:\n{actual}\nvs\n{expected}'
        assert np.allclose(actual, axis[order[2]] @ axis[order[1]] @ axis[order[0]])


def test_rotation_matrix_from_euler_rejects_bad_order():
    with pytest.raises(ValueError, match='Unsupported Euler order'):
        Object3D.rotation_matrix_from_euler(0, 0, 0, 'XYY')  # type: ignore[arg-type]


def test_polyline(screen: Screen):
    scene = None
    line_obj = None

    @ui.page('/')
    def page():
        nonlocal scene, line_obj
        with ui.scene() as scene:
            line_obj = scene.polyline(
                points=[[0, 0, 0], [1, 0, 0], [1, 1, 0]],
                colors=[[1, 0, 0], [0, 1, 0], [0, 0, 1]],
                dashed=True,
                dash_size=0.1,
                gap_size=0.05,
            )

    screen.open('/')
    screen.wait(0.5)
    is_line = screen.selenium.execute_script(
        f'const o = getElement({scene.id}).objects.get("{line_obj.id}").mesh;'
        'return o.isLine === true && o.material.type === "LineDashedMaterial" && o.material.vertexColors === true;'
    )
    assert is_line


def test_lathe(screen: Screen):
    scene = None
    obj = None

    @ui.page('/')
    def page():
        nonlocal scene, obj
        with ui.scene() as scene:
            obj = scene.lathe(points=[[0, 0], [0.5, 0.5], [0, 1]], segments=8)

    screen.open('/')
    screen.wait(0.5)
    is_lathe = screen.selenium.execute_script(
        f'const o = getElement({scene.id}).objects.get("{obj.id}").mesh;'
        'return o.isMesh === true && o.geometry.type === "LatheGeometry";'
    )
    assert is_lathe


def test_polyline_rejects_mismatched_colors():
    from nicegui.elements.scene.objects import Polyline
    with pytest.raises(ValueError, match='colors length'):
        Polyline(points=[[0, 0, 0], [1, 0, 0]], colors=[[1, 0, 0]])


def test_polyline_rejects_too_few_points():
    from nicegui.elements.scene.objects import Polyline
    with pytest.raises(ValueError, match='at least 2'):
        Polyline(points=[[0, 0, 0]])


@pytest.mark.parametrize('polar_grid,expected_vertex_count', [
    # PolarGridHelper(radius, sectors, rings, divisions) vertex count = sectors*2 + rings*divisions*2.
    ((1.0, 8, 5), 8 * 2 + 5 * 64 * 2),       # default divisions=64
    ((1.0, 8, 5, 128), 8 * 2 + 5 * 128 * 2),  # explicit divisions=128
])
def test_polar_grid_smoothness(screen: Screen, polar_grid: tuple, expected_vertex_count: int):
    scene = None

    @ui.page('/')
    def page():
        nonlocal scene
        with ui.scene(grid=False, polar_grid=polar_grid) as scene:
            scene.sphere(0.1).move(0.5, 0, 0)

    screen.open('/')
    screen.wait(0.5)
    # children: ambient light, directional light, circular ground, polar grid helper, sphere
    assert screen.selenium.execute_script(f'return scene_{scene.html_id}.children.length') == 5
    helper_vertex_count = screen.selenium.execute_script(
        f'return scene_{scene.html_id}.children[3].geometry.attributes.position.count'
    )
    assert helper_vertex_count == expected_vertex_count


@pytest.mark.parametrize('factory_name,three_geometry', [
    ('plane', 'PlaneGeometry'),
    ('cone', 'ConeGeometry'),
    ('torus', 'TorusGeometry'),
    ('capsule', 'CapsuleGeometry'),
])
def test_geometry_primitive(screen: Screen, factory_name: str, three_geometry: str):
    """Smoke test that each primitive dispatches to the expected Three.js geometry class.

    Catches silent removals or renames in future Three.js upgrades.
    """
    scene = None
    obj = None

    @ui.page('/')
    def page():
        nonlocal scene, obj
        with ui.scene() as scene:
            obj = getattr(scene, factory_name)()

    screen.open('/')
    screen.wait(0.5)
    is_expected = screen.selenium.execute_script(
        f'const o = getElement({scene.id}).objects.get("{obj.id}").mesh;'
        f'return o.isMesh === true && o.geometry.type === "{three_geometry}";'
    )
    assert is_expected


def test_rotate_with_order(screen: Screen):
    scene = None
    box = None

    @ui.page('/')
    def page():
        nonlocal scene, box
        with ui.scene() as scene:
            box = scene.box().rotate(0.4, -0.3, 0.5, order='ZYX')

    screen.open('/')
    screen.wait(0.5)
    expected = Object3D.rotation_matrix_from_euler(0.4, -0.3, 0.5, 'ZYX')
    assert np.allclose(box.R, expected)
    server_R = screen.selenium.execute_script(
        f'const o = getElement({scene.id}).objects.get("{box.id}").mesh;'
        'const m = o.matrixWorld.elements;'
        # Three.js stores column-major; pull out the upper-left 3x3.
        'return [[m[0], m[4], m[8]], [m[1], m[5], m[9]], [m[2], m[6], m[10]]];'
    )
    assert np.allclose(server_R, expected, atol=1e-6)


def _wait_for_scene_ready(screen: Screen, scene_id: int) -> None:
    screen.wait_for(lambda: screen.selenium.execute_script(
        f'return !!getElement({scene_id}) && !!getElement({scene_id}).renderer'
    ))


def _count_clipping_planes(screen: Screen, scene_id: int, object_id: str) -> int:
    return screen.selenium.execute_script(
        f'const el = getElement({scene_id});'
        # -1 while the scene or object is (re-)mounting, so wait_for polls instead of raising
        'if (!el || !el.objects) return -1;'
        f'const record = el.objects.get("{object_id}");'
        'if (!record || !record.mesh) return -1;'
        'let n = 0;'
        'record.mesh.traverse((c) => {'
        '  if (!c.material) return;'
        '  const mats = Array.isArray(c.material) ? c.material : [c.material];'
        '  for (const m of mats) if (m.clippingPlanes) n += m.clippingPlanes.length;'
        '});'
        'return n;'
    )


def test_set_clipping_planes(screen: Screen):
    from nicegui import events
    scene = None
    box = None

    @ui.page('/')
    def page():
        nonlocal scene, box
        with ui.scene() as scene:
            box = scene.box()

    screen.open('/')
    _wait_for_scene_ready(screen, scene.id)
    box.set_clipping_planes([events.SceneClipPlane(nx=0, ny=0, nz=1, d=0)])
    screen.wait_for(lambda: _count_clipping_planes(screen, scene.id, box.id) >= 1)
    box.clear_clipping_planes()
    screen.wait_for(lambda: _count_clipping_planes(screen, scene.id, box.id) == 0)


def test_clipping_planes_survive_context_loss(screen: Screen):
    from nicegui import events
    scene = None
    box = None

    @ui.page('/')
    def page():
        nonlocal scene, box
        with ui.scene() as scene:
            box = scene.box()

    screen.open('/')
    _wait_for_scene_ready(screen, scene.id)
    box.set_clipping_planes([events.SceneClipPlane(nx=0, ny=0, nz=1, d=2)])
    screen.wait_for(lambda: _count_clipping_planes(screen, scene.id, box.id) >= 1)

    # _resend() must replay the planes when the scene remounts after a WebGL context loss.
    screen.selenium.execute_script(
        'document.querySelector("canvas").getContext("webgl2").getExtension("WEBGL_lose_context").loseContext();'
    )
    screen.click('Click to re-initialize')
    screen.wait_for(lambda: _count_clipping_planes(screen, scene.id, box.id) >= 1)


def test_intersection_planes_in_click_event(screen: Screen):
    from nicegui import events
    scene = None
    intersections: list = []

    @ui.page('/')
    def page():
        nonlocal scene

        def handle(e: events.SceneClickEventArguments):
            intersections.append(e.intersections)
        scene = ui.scene(
            on_click=handle,
            intersection_planes=[
                events.SceneIntersectionPlane(name='ground', axis='z', offset=0),
                events.SceneIntersectionPlane(name='wall', axis='x', offset=2),
            ],
        )

    screen.open('/')
    _wait_for_scene_ready(screen, scene.id)
    canvas = screen.find_by_tag('canvas')
    canvas.click()
    screen.wait_for(lambda: bool(intersections))
    keys = set(intersections[0].keys())
    assert keys == {'ground', 'wall'}


async def test_intersection_planes_validation(user: User):
    from nicegui import events

    with pytest.raises(ValueError, match='axis'):
        events.SceneIntersectionPlane(name='foo', axis='w')  # type: ignore[arg-type]

    @ui.page('/')
    def page():
        with pytest.raises(ValueError, match=r'[Dd]uplicate'):
            ui.scene(intersection_planes=[
                events.SceneIntersectionPlane(name='dup'),
                events.SceneIntersectionPlane(name='dup'),
            ])
        ui.label('ok')

    await user.open('/')
    await user.should_see('ok')


def test_raycaster_threshold_runtime_change(screen: Screen):
    scene = None

    @ui.page('/')
    def page():
        nonlocal scene
        scene = ui.scene(raycaster_threshold=0.05)

    screen.open('/')
    _wait_for_scene_ready(screen, scene.id)
    assert screen.selenium.execute_script(
        f'return getElement({scene.id})._raycaster.params.Line.threshold'
    ) == 0.05
    scene._props['raycaster-threshold'] = 0.5
    scene.update()
    screen.wait_for(lambda: screen.selenium.execute_script(
        f'return getElement({scene.id})._raycaster.params.Line.threshold'
    ) == 0.5)


async def test_axes_inset_opts_cached_for_replay_on_init(user: User):
    # The reload-survival contract: state set via set_axes_inset/set_axes_labels is cached on
    # Scene and replayed in _handle_init, so a fresh client connect re-applies the inset.
    scene = None

    @ui.page('/')
    def page():
        nonlocal scene
        scene = ui.scene()

    await user.open('/')
    assert scene._axes_inset_opts is None
    assert scene._axes_labels_opts is None
    scene.set_axes_inset(enabled=True, anchor='top-left', margin=8)
    assert scene._axes_inset_opts == {
        'enabled': True, 'marginX': 8, 'marginY': 8, 'anchor': 'top-left',
    }
    scene.set_axes_labels(enabled=True, labels=('A', 'B', 'C'), color='#ff0000')
    assert scene._axes_labels_opts == {
        'enabled': True, 'labels': ['A', 'B', 'C'],
        'font': '24px Arial', 'color': '#ff0000', 'radius': 14,
    }


def test_set_axes_inset_and_labels(screen: Screen):
    scene = None

    @ui.page('/')
    def page():
        nonlocal scene
        scene = ui.scene()

    screen.open('/')
    _wait_for_scene_ready(screen, scene.id)

    scene.set_axes_inset(enabled=True, anchor='top-left', margin=8)
    screen.wait_for(lambda: screen.selenium.execute_script(
        f'return !!getElement({scene.id}).viewHelper'
    ))
    # location is what the r184 ViewHelper reads to position the inset; verify it matches.
    location = screen.selenium.execute_script(
        f'return getElement({scene.id}).viewHelper.location'
    )
    assert location == {'top': 8, 'bottom': None, 'left': 8, 'right': None}

    # Labels and style are forwarded to viewHelper.setLabels / setLabelStyle. The cached opts
    # on the JS side are the most stable observable across three.js versions; deeper checks
    # against sprite material uuids are brittle.
    scene.set_axes_labels(enabled=True, labels=('Forward', 'Left', 'Up'),
                          font='20px sans-serif', color='#ff0000', radius=18)
    screen.wait_for(lambda: screen.selenium.execute_script(
        f'const el = getElement({scene.id});'
        'return el.viewHelper && el._axesLabels && el._axesLabels.color === "#ff0000"'
    ))

    # Toggling enabled=False rebuilds a fresh ViewHelper on re-enable; the cached labels/style
    # must be reapplied so users don't lose their configuration.
    scene.set_axes_inset(enabled=False)
    screen.wait_for(lambda: not screen.selenium.execute_script(
        f'return !!getElement({scene.id}).viewHelper'
    ))
    scene.set_axes_inset(enabled=True, anchor='top-left', margin=8)
    screen.wait_for(lambda: screen.selenium.execute_script(
        f'const el = getElement({scene.id});'
        'return !!el.viewHelper && el._axesLabels && el._axesLabels.color === "#ff0000"'
    ))


def test_axes_inset_preserves_main_scene_render(screen: Screen):
    """``viewHelper.render()`` clears the framebuffer when ``renderer.autoClear`` is true,
    which wipes the main scene one draw after it renders. The render loop must save/restore
    ``autoClear`` around the helper call so the main scene survives each frame."""
    scene = None

    @ui.page('/')
    def page():
        nonlocal scene
        scene = ui.scene()

    screen.open('/')
    _wait_for_scene_ready(screen, scene.id)
    scene.set_axes_inset(enabled=True)
    screen.wait_for(lambda: screen.selenium.execute_script(
        f'return !!getElement({scene.id}).viewHelper'
    ))
    # Patch viewHelper.render to record renderer.autoClear at call time. The render loop
    # must drop it to false before the helper draws — otherwise the helper wipes the main
    # scene's framebuffer.
    screen.selenium.execute_script(
        f'const el = getElement({scene.id});'
        'const orig = el.viewHelper.render.bind(el.viewHelper);'
        'window.__autoClearLog = [];'
        'el.viewHelper.render = function (renderer) {'
        '  window.__autoClearLog.push(renderer.autoClear);'
        '  return orig(renderer);'
        '};'
    )
    # Let the rAF loop run several frames.
    screen.wait(0.3)
    log = screen.selenium.execute_script('return window.__autoClearLog')
    assert len(log) >= 2, f'expected multiple viewHelper.render calls, got {log}'
    assert all(v is False for v in log), \
        f'renderer.autoClear must be false during viewHelper.render; got {log}'


def test_axes_inset_handle_click_snaps_camera(screen: Screen):
    scene = None

    @ui.page('/')
    def page():
        nonlocal scene
        scene = ui.scene()

    screen.open('/')
    _wait_for_scene_ready(screen, scene.id)
    scene.set_axes_inset(enabled=True)  # default anchor='bottom-right', margin=0
    screen.wait_for(lambda: screen.selenium.execute_script(
        f'return !!getElement({scene.id}).viewHelper'
    ))

    # +X axis sprite is at world (1, 0, 0), which projects to inset NDC (0.5, 0) in the
    # orthoCamera's [-2, 2, -2, 2] frustum. Dispatch a pointerdown at that pixel and verify
    # viewHelper.animating flips on (then off when the snap-animation completes). Inset is
    # 128 px hardcoded inside three.js' ViewHelper; we use anchor=bottom-right, margin=0.
    animating = screen.selenium.execute_script(
        f'const el = getElement({scene.id});'
        'const canvas = el.renderer.domElement;'
        'const dim = 128;'
        'const relX = (0.5 + 1) / 2 * dim;'
        'const relY = (1 - 0) / 2 * dim;'
        'const insetLeft = canvas.clientWidth - dim;'
        'const insetTop = canvas.clientHeight - dim;'
        'const rect = canvas.getBoundingClientRect();'
        'canvas.dispatchEvent(new PointerEvent("pointerdown", {'
        '  clientX: rect.left + insetLeft + relX,'
        '  clientY: rect.top + insetTop + relY,'
        '  bubbles: true, cancelable: true'
        '}));'
        'return el.viewHelper.animating;'
    )
    assert animating, 'Clicking the +X axis sprite should set viewHelper.animating = true'
    screen.wait_for(lambda: not screen.selenium.execute_script(
        f'return getElement({scene.id}).viewHelper.animating'
    ))


def test_pointer_capture_keeps_the_drag_on_the_object(screen: Screen):
    """A drag that starts on a captured object keeps reporting to it after the pointer has left it and the canvas."""
    events: list[tuple[str, str, float | None, float | None, float | None]] = []
    hover_events: list[str] = []
    scene = None
    box = None

    @ui.page('/')
    def page():
        nonlocal scene, box

        def record(e: ScenePointerEventArguments) -> None:
            events.append((e.type, e.pointer_type, e.x, e.y, e.z))
        with ui.scene() as scene:
            box = scene.box().capture_pointer() \
                .on_pointer_down(record).on_pointer_move(record).on_pointer_up(record) \
                .on_pointer_over(lambda: hover_events.append('over')) \
                .on_pointer_out(lambda: hover_events.append('out'))

    screen.open('/')
    screen.wait_for(lambda: screen.selenium.execute_script(
        f'return getElement({scene.id}).has_handler("{box.id}", "pointerup")'
    ))

    def dispatch(event_type: str, target: str, dx: int) -> None:
        # the camera looks at the box, so the canvas center hits it; `dx` moves the pointer along that row
        screen.selenium.execute_script(f'''
            const el = getElement({scene.id});
            const rect = el.renderer.domElement.getBoundingClientRect();
            {target}.dispatchEvent(new PointerEvent("{event_type}", {{
                bubbles: true, pointerId: 1, pointerType: "mouse", button: 0,
                clientX: rect.left + rect.width / 2 + {dx}, clientY: rect.top + rect.height / 2,
            }}));
        ''')

    def orbit_enabled() -> bool:
        return screen.selenium.execute_script(f'return getElement({scene.id}).controls.enabled')

    dispatch('pointermove', 'el.renderer.domElement', 0)
    screen.wait_for(lambda: hover_events == ['over'])
    events.clear()
    dispatch('pointerdown', 'el.renderer.domElement', 0)
    screen.wait_for(lambda: any(type_ == 'pointerdown' for type_, *_ in events))
    assert orbit_enabled() is False

    dispatch('pointermove', 'window', -300)  # well outside the box and the 400px canvas
    screen.wait_for(lambda: any(type_ == 'pointermove' for type_, *_ in events))
    dispatch('pointerup', 'window', -300)
    screen.wait_for(lambda: any(type_ == 'pointerup' for type_, *_ in events))
    screen.wait_for(orbit_enabled)
    screen.wait_for(lambda: hover_events == ['over', 'out'])

    assert [type_ for type_, *_ in events] == ['pointerdown', 'pointermove', 'pointerup']
    assert events[0][1:] == ('mouse', pytest.approx(0, abs=1e-6), pytest.approx(0, abs=1e-6), 0)
    for _, pointer_type, x, y, z in events[1:]:
        assert pointer_type == 'mouse'
        assert x < -0.5, 'the pointer ray meets the box plane left of the box'
        assert y == pytest.approx(0, abs=1e-6)
        assert z == 0


def test_transform_controls_handle_keeps_target_hovered(screen: Screen):
    """Hovering a TransformControls handle does not count as leaving the object it belongs to."""
    events: list[str] = []
    scene = None
    box = None

    @ui.page('/')
    def page():
        nonlocal scene, box
        with ui.scene() as scene:
            box = scene.box() \
                .on_pointer_over(lambda e: events.append(e.type)) \
                .on_pointer_out(lambda e: events.append(e.type))
            box.enable_transform_controls(mode='translate')

    screen.open('/')
    screen.wait_for(lambda: screen.selenium.execute_script(
        f'const el = getElement({scene.id});'
        f'return el.has_transform_controls("{box.id}") && el.has_handler("{box.id}", "pointerout")'
    ))

    def move_pointer(dx: int, *, axis: str | None) -> None:
        # `axis` is what the gizmo's own hover raycast reports; a synthesized move without pointer type leaves it alone
        screen.selenium.execute_script(f'''
            const el = getElement({scene.id});
            el.transform_controls.get("{box.id}").axis = {'null' if axis is None else f'"{axis}"'};
            const rect = el.renderer.domElement.getBoundingClientRect();
            el.renderer.domElement.dispatchEvent(new PointerEvent("pointermove", {{
                bubbles: true, pointerId: 1,
                clientX: rect.left + rect.width / 2 + {dx}, clientY: rect.top + rect.height / 2,
            }}));
        ''')

    def cursor() -> str:
        return screen.selenium.execute_script(f'return getElement({scene.id}).renderer.domElement.style.cursor')

    move_pointer(0, axis=None)
    screen.wait_for(lambda: events == ['pointerover'])
    move_pointer(-150, axis='X')
    assert cursor() == 'pointer'
    move_pointer(-150, axis=None)
    screen.wait_for(lambda: events == ['pointerover', 'pointerout'])
    assert cursor() == ''


def test_deleting_objects_releases_renderer_geometry(screen: Screen):
    """Repeatedly showing and deleting a handle must not grow GPU allocations."""
    scene = None
    handles = []

    @ui.page('/')
    def page():
        nonlocal scene
        with ui.scene() as scene:
            scene.box().move(2, 0, 0)

        def show():
            with scene, scene.group() as handle:
                scene.box(1, 1, 0.1)
                scene.sphere(0.1)
            handles.append(handle)

        ui.button('Show handle', on_click=show)
        ui.button('Hide handle', on_click=lambda: handles.pop().delete())

    screen.open('/')

    def geometries():
        return screen.selenium.execute_script(
            f'return getElement({scene.id}).renderer.info.memory.geometries'
        )

    screen.wait_for(lambda: geometries() > 0)
    baseline = geometries()
    for _ in range(3):
        screen.click('Show handle')
        screen.wait_for(lambda: geometries() == baseline + 2)
        screen.click('Hide handle')
        screen.wait_for(lambda: geometries() == baseline)
