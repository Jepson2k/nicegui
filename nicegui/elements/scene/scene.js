import SceneLib from "nicegui-scene";
const {
  CSS2DObject,
  CSS2DRenderer,
  CSS3DObject,
  CSS3DRenderer,
  DragControls,
  GLTFLoader,
  OrbitControls,
  STLLoader,
  TransformControls,
  THREE,
  TWEEN,
  Stats,
} = SceneLib;

function texture_geometry(coords) {
  const geometry = new THREE.BufferGeometry();
  const nI = coords[0].length;
  const nJ = coords.length;
  const vertices = [];
  const indices = [];
  const uvs = [];
  for (let j = 0; j < nJ; ++j) {
    for (let i = 0; i < nI; ++i) {
      const XYZ = coords[j][i] || [0, 0, 0];
      vertices.push(...XYZ);
      uvs.push(i / (nI - 1), j / (nJ - 1));
    }
  }
  for (let j = 0; j < nJ - 1; ++j) {
    for (let i = 0; i < nI - 1; ++i) {
      if (coords[j][i] && coords[j][i + 1] && coords[j + 1][i] && coords[j + 1][i + 1]) {
        const idx00 = i + j * nI;
        const idx10 = i + j * nI + 1;
        const idx01 = i + j * nI + nI;
        const idx11 = i + j * nI + 1 + nI;
        indices.push(idx10, idx00, idx01);
        indices.push(idx11, idx10, idx01);
      }
    }
  }
  geometry.setIndex(new THREE.Uint32BufferAttribute(indices, 1));
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(vertices, 3));
  geometry.setAttribute("uv", new THREE.Float32BufferAttribute(uvs, 2));
  geometry.computeVertexNormals();
  return geometry;
}

function texture_material(texture) {
  texture.flipY = false;
  texture.minFilter = THREE.LinearFilter;
  return new THREE.MeshLambertMaterial({
    map: texture,
    side: THREE.DoubleSide,
    transparent: true,
  });
}

function set_point_cloud_data(position, color, geometry) {
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(position.flat(), 3));
  if (color === null) {
    geometry.deleteAttribute("color");
  } else {
    geometry.setAttribute("color", new THREE.Float32BufferAttribute(color.flat(), 3));
  }
}

export default {
  template: `
    <div style="position:relative" data-initializing>
      <canvas style="position:relative"></canvas>
      <div style="position:absolute;pointer-events:none;top:0"></div>
      <div style="position:absolute;pointer-events:none;top:0"></div>
    </div>`,

  mounted() {
    this.scene = new THREE.Scene();
    this.objects = new Map();
    this.objects.set("scene", this.scene);
    this.draggable_objects = [];
    this.transform_controls = new Map(); // object_id -> TransformControls instance
    this.is_initialized = false;
    this.dragging_count = 0; // Reference count for TransformControls dragging - only enable orbit when 0

    if (this.show_stats) {
      this.stats = new Stats();
      this.stats.domElement.style.position = "absolute";
      this.stats.domElement.style.top = "0px";
      this.$el.appendChild(this.stats.domElement);
    }

    window["scene_" + this.$el.id] = this.scene; // NOTE: for selenium tests only

    if (this.camera_type === "perspective") {
      this.camera = new THREE.PerspectiveCamera(
        this.camera_params.fov,
        this.width / this.height,
        this.camera_params.near,
        this.camera_params.far
      );
    } else {
      this.camera = new THREE.OrthographicCamera(
        (-this.camera_params.size / 2) * (this.width / this.height),
        (this.camera_params.size / 2) * (this.width / this.height),
        this.camera_params.size / 2,
        -this.camera_params.size / 2,
        this.camera_params.near,
        this.camera_params.far
      );
    }
    this.look_at = new THREE.Vector3(0, 0, 0);
    this.camera.lookAt(this.look_at);
    this.camera.up = new THREE.Vector3(0, 0, 1);
    this.camera.position.set(0, -3, 5);

    this.scene.add(new THREE.AmbientLight(0xffffff, 0.7 * Math.PI));
    const light = new THREE.DirectionalLight(0xffffff, 0.3 * Math.PI);
    light.position.set(5, 10, 40);
    this.scene.add(light);

    this.renderer = undefined;
    try {
      this.renderer = new THREE.WebGLRenderer({
        antialias: true,
        alpha: true,
        canvas: this.$el.children[0],
      });
      // Enable local clipping planes for proximity-based envelope visibility
      this.renderer.localClippingEnabled = true;
    } catch {
      this.$el.innerHTML = "Could not create WebGL renderer.";
      this.$el.style.width = this.width + "px";
      this.$el.style.height = this.height + "px";
      this.$el.style.padding = "10px";
      this.$el.style.border = "1px solid silver";
      return;
    }
    this.renderer.setClearColor(this.background_color);
    this.renderer.setSize(this.width, this.height);

    this.text_renderer = new CSS2DRenderer({
      element: this.$el.children[1],
    });
    this.text_renderer.setSize(this.width, this.height);

    this.text3d_renderer = new CSS3DRenderer({
      element: this.$el.children[2],
    });
    this.text3d_renderer.setSize(this.width, this.height);

    // Orientation inset: opt-in and lazy (created via set_axes_inset({enabled:true}))
    this._axes = {};

    this.$nextTick(() => this.resize());
    window.addEventListener("resize", this.resize, false);
    window.addEventListener("DOMContentLoaded", this.resize, false);

    // Create polar or rectangular grid depending on props (mutually exclusive, polar takes precedence)
    if (this.polar_grid) {
      // polar_grid is [radius, sectors, rings]
      const radius = this.polar_grid[0] || 1.0;
      const sectors = this.polar_grid[1] || 10;
      const rings = this.polar_grid[2] || 10;
      
      // Create circular ground plane
      const ground = new THREE.Mesh(
        new THREE.CircleGeometry(radius, 64),
        new THREE.MeshPhongMaterial({ color: this.background_color })
      );
      ground.translateZ(-0.01);
      ground.object_id = "ground";
      this.scene.add(ground);

      // Create polar grid helper
      const polarGrid = new THREE.PolarGridHelper(radius, sectors, rings, 64);
      polarGrid.material.transparent = true;
      polarGrid.material.opacity = 0.3;
      polarGrid.rotateX(Math.PI / 2); // Convert to XY plane (Z-up)
      this.scene.add(polarGrid);
    } else if (this.grid) {
      const gridSize = this.grid[0] || 100;
      const gridDivisions = this.grid[1] || 100;
      const ground = new THREE.Mesh(
        new THREE.PlaneGeometry(gridSize, gridSize),
        new THREE.MeshPhongMaterial({ color: this.background_color })
      );
      ground.translateZ(-0.01);
      ground.object_id = "ground";
      this.scene.add(ground);

      const grid = new THREE.GridHelper(gridSize, gridDivisions);
      grid.material.transparent = true;
      grid.material.opacity = 0.2;
      grid.rotateX(Math.PI / 2);
      this.scene.add(grid);
    }
    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.drag_controls = new DragControls(this.draggable_objects, this.camera, this.renderer.domElement);
    this.drag_controls.transformGroup = true;
    const applyConstraint = (constraint, position) => {
      if (!constraint) return;
      const [variable, expression] = constraint.split("=").map((s) => s.trim());
      position[variable] = eval(expression.replace(/x|y|z/g, (match) => `(${position[match]})`));
    };
    const handleDrag = (event) => {
      this.drag_constraints.split(",").forEach((constraint) => applyConstraint(constraint, event.object.position));
      this.$emit(event.type, {
        type: event.type,
        object_id: event.object.object_id,
        object_name: event.object.name,
        x: event.object.position.x,
        y: event.object.position.y,
        z: event.object.position.z,
      });
      if (event.type === "dragstart") this.controls.enabled = false;
      if (event.type === "dragend") this.controls.enabled = true;
    };
    this.drag_controls.addEventListener("dragstart", handleDrag);
    this.drag_controls.addEventListener("drag", handleDrag);
    this.drag_controls.addEventListener("dragend", handleDrag);

    const render = () => {
      requestAnimationFrame(() => setTimeout(() => render(), 1000 / this.fps));
      this.camera_tween?.update();
      // Ensure full-canvas viewport and no scissor before main render
      const canvas = this.renderer.domElement;
      this.renderer.setViewport(0, 0, canvas.width, canvas.height);
      this.renderer.setScissorTest(false);
      this.renderer.render(this.scene, this.camera);
      this.text_renderer.render(this.scene, this.camera);
      this.text3d_renderer.render(this.scene, this.camera);

      // Render camera orientation axes inset (bottom-left)
      if (this.axesScene && this.axesCamera) {
        const size = (this._axes && this._axes.size) ? this._axes.size : 96;
        const margin = (this._axes && this._axes.margin) ? this._axes.margin : 10;

        // Sync the inset camera orientation with the main camera using orbit direction
        const target = (this.controls && this.controls.target) ? this.controls.target : (this.look_at || new THREE.Vector3(0, 0, 0));
        const cameraDir = this.camera.position.clone().sub(target).normalize();
        this.axesCamera.position.copy(cameraDir).multiplyScalar(2);
        this.axesCamera.lookAt(0, 0, 0);
        this.axesCamera.up.copy(this.camera.up);
        this.axesCamera.updateProjectionMatrix();

        // Draw into a scissored viewport with configurable anchor and margins (scale by device pixel ratio)
        const pr = (this.renderer.getPixelRatio?.() ?? window.devicePixelRatio ?? 1);
        const mx = Math.floor(((this._axes && this._axes.marginX) ?? margin) * pr);
        const my = Math.floor(((this._axes && this._axes.marginY) ?? margin) * pr);
        const vw = Math.floor(size * pr);
        const vh = Math.floor(size * pr);
        const anchor = (this._axes && this._axes.anchor) ? this._axes.anchor : "bottom-left";
        const canvasEl = this.renderer.domElement;
        let vx = mx;
        let vy = my;
        if (anchor === "bottom-right") {
          vx = canvasEl.width - vw - mx;
          vy = my;
        } else if (anchor === "top-left") {
          vx = mx;
          vy = canvasEl.height - vh - my;
        } else if (anchor === "top-right") {
          vx = canvasEl.width - vw - mx;
          vy = canvasEl.height - vh - my;
        }
        this.renderer.setScissorTest(true);
        this.renderer.setViewport(vx, vy, vw, vh);
        this.renderer.setScissor(vx, vy, vw, vh);

        // Render inset without clearing color (transparent overlay)
        const prevAutoClear = this.renderer.autoClear;
        this.renderer.autoClear = false;
        this.renderer.clearDepth();
        this.renderer.render(this.axesScene, this.axesCamera);
        this.renderer.autoClear = prevAutoClear;

        // Restore scissor and full viewport for subsequent renders
        this.renderer.setScissorTest(false);
        const canvas = this.renderer.domElement;
        this.renderer.setViewport(0, 0, canvas.width, canvas.height);
      }

      if (this.stats) this.stats.update();
    };
    render();

    const raycaster = new THREE.Raycaster();

    // Ground plane for ray-plane intersection (Z=0)
    const groundPlane = new THREE.Plane(new THREE.Vector3(0, 0, 1), 0);

    const click_handler = (mouseEvent) => {
      let x = (mouseEvent.offsetX / this.renderer.domElement.width) * 2 - 1;
      let y = -(mouseEvent.offsetY / this.renderer.domElement.height) * 2 + 1;
      raycaster.setFromCamera({ x: x, y: y }, this.camera);

      // Compute ray-plane intersection with Z=0 ground plane
      // This gives consistent coordinates even when clicking on "empty space"
      const groundIntersection = new THREE.Vector3();
      const hasGroundIntersection = raycaster.ray.intersectPlane(groundPlane, groundIntersection);

      this.$emit("click3d", {
        hits: raycaster
          .intersectObjects(this.scene.children, true)
          .filter((o) => o.object.object_id)
          .map((o) => ({
            object_id: o.object.object_id,
            object_name: o.object.name,
            point: o.point,
          })),
        // Ground plane intersection point (Z=0) - works even in empty space
        ground_point: hasGroundIntersection ? {
          x: groundIntersection.x,
          y: groundIntersection.y,
          z: groundIntersection.z,
        } : null,
        click_type: mouseEvent.type,
        button: mouseEvent.button,
        alt_key: mouseEvent.altKey,
        ctrl_key: mouseEvent.ctrlKey,
        meta_key: mouseEvent.metaKey,
        shift_key: mouseEvent.shiftKey,
        // Screen coordinates for drag detection
        screen_x: mouseEvent.screenX,
        screen_y: mouseEvent.screenY,
        client_x: mouseEvent.clientX,
        client_y: mouseEvent.clientY,
        offset_x: mouseEvent.offsetX,
        offset_y: mouseEvent.offsetY,
      });
    };
    this.click_events.forEach((event) => this.$el.addEventListener(event, click_handler));

    this.texture_loader = new THREE.TextureLoader();
    this.stl_loader = new STLLoader();
    this.gltf_loader = new GLTFLoader();

    const connectInterval = setInterval(() => {
      if (window.socket.id === undefined) return;
      this.$emit("init");
      clearInterval(connectInterval);
    }, 100);
  },

  beforeUnmount() {
    window.removeEventListener("resize", this.resize);
    window.removeEventListener("DOMContentLoaded", this.resize);
  },

  methods: {
    create(type, id, parent_id, ...args) {
      if (!this.is_initialized) return;
      let mesh;
      if (type == "group") {
        mesh = new THREE.Group();
      } else if (type == "line") {
        const start = new THREE.Vector3(...args[0]);
        const end = new THREE.Vector3(...args[1]);
        const geometry = new THREE.BufferGeometry().setFromPoints([start, end]);
        const material = new THREE.LineBasicMaterial({ transparent: true });
        mesh = new THREE.Line(geometry, material);
      } else if (type == "curve") {
        const curve = new THREE.CubicBezierCurve3(
          new THREE.Vector3(...args[0]),
          new THREE.Vector3(...args[1]),
          new THREE.Vector3(...args[2]),
          new THREE.Vector3(...args[3])
        );
        const points = curve.getPoints(args[4] - 1);
        const geometry = new THREE.BufferGeometry().setFromPoints(points);
        const material = new THREE.LineBasicMaterial({ transparent: true });
        mesh = new THREE.Line(geometry, material);
      } else if (type == "text") {
        const div = document.createElement("div");
        div.textContent = args[0];
        div.style.cssText = args[1];
        mesh = new CSS2DObject(div);
      } else if (type == "text3d") {
        const div = document.createElement("div");
        div.textContent = args[0];
        div.style.cssText = "userSelect:none;" + args[1];
        mesh = new CSS3DObject(div);
      } else if (type == "texture") {
        const url = args[0];
        const coords = args[1];
        const geometry = texture_geometry(coords);
        const material = texture_material(this.texture_loader.load(url));
        mesh = new THREE.Mesh(geometry, material);
      } else if (type == "spot_light") {
        mesh = new THREE.Group();
        const light = new THREE.SpotLight(...args);
        light.position.set(0, 0, 0);
        light.target = new THREE.Object3D();
        light.target.position.set(1, 0, 0);
        mesh.add(light);
        mesh.add(light.target);
      } else if (type == "point_cloud") {
        const geometry = new THREE.BufferGeometry();
        const material = new THREE.PointsMaterial({ size: args[2], transparent: true });
        set_point_cloud_data(args[0], args[1], geometry);
        mesh = new THREE.Points(geometry, material);
      } else if (type == "gltf") {
        const url = args[0];
        mesh = new THREE.Group();
        this.gltf_loader.load(
          url,
          (gltf) => mesh.add(gltf.scene),
          undefined,
          (error) => console.error(error)
        );
      } else if (type == "axes_helper") {
        mesh = new THREE.AxesHelper(args[0]);
        mesh.material.transparent = true;
      } else {
        let geometry;
        const wireframe = args.pop();
        if (type == "box") geometry = new THREE.BoxGeometry(...args);
        if (type == "sphere") geometry = new THREE.SphereGeometry(...args);
        if (type == "cylinder") geometry = new THREE.CylinderGeometry(...args);
        if (type == "ring") geometry = new THREE.RingGeometry(...args);
        if (type == "quadratic_bezier_tube") {
          const curve = new THREE.QuadraticBezierCurve3(
            new THREE.Vector3(...args[0]),
            new THREE.Vector3(...args[1]),
            new THREE.Vector3(...args[2])
          );
          geometry = new THREE.TubeGeometry(curve, ...args.slice(3));
        }
        if (type == "extrusion") {
          const shape = new THREE.Shape();
          const outline = args[0];
          const height = args[1];
          shape.autoClose = true;
          if (outline.length) {
            shape.moveTo(outline[0][0], outline[0][1]);
            outline.slice(1).forEach((p) => shape.lineTo(p[0], p[1]));
          }
          const settings = { depth: height, bevelEnabled: false };
          geometry = new THREE.ExtrudeGeometry(shape, settings);
        }
        if (type == "stl") {
          const url = args[0];
          geometry = new THREE.BufferGeometry();
          this.stl_loader.load(url, (geometry) => (mesh.geometry = geometry));
        }
        let material;
        if (wireframe) {
          mesh = new THREE.LineSegments(
            new THREE.EdgesGeometry(geometry),
            new THREE.LineBasicMaterial({ transparent: true })
          );
        } else {
          material = new THREE.MeshPhongMaterial({ transparent: true });
          mesh = new THREE.Mesh(geometry, material);
        }
      }
      mesh.object_id = id;
      this.objects.set(id, mesh);
      this.objects.get(parent_id).add(this.objects.get(id));
    },
    name(object_id, name) {
      if (!this.objects.has(object_id)) return;
      this.objects.get(object_id).name = name;
    },
    material(object_id, color, opacity, side) {
      if (!this.objects.has(object_id)) return;
      const material = this.objects.get(object_id).material;
      if (!material) return;
      const vertexColors = color === null;
      material.color.set(vertexColors ? "#ffffff" : color);
      material.needsUpdate = material.vertexColors != vertexColors;
      material.vertexColors = vertexColors;
      material.opacity = opacity;
      if (side == "front") material.side = THREE.FrontSide;
      else if (side == "back") material.side = THREE.BackSide;
      else material.side = THREE.DoubleSide;
    },
    move(object_id, x, y, z) {
      if (!this.objects.has(object_id)) return;
      this.objects.get(object_id).position.set(x, y, z);
    },
    scale(object_id, sx, sy, sz) {
      if (!this.objects.has(object_id)) return;
      this.objects.get(object_id).scale.set(sx, sy, sz);
    },
    rotate(object_id, R) {
      if (!this.objects.has(object_id)) return;
      const R4 = new THREE.Matrix4().makeBasis(
        new THREE.Vector3(...R[0]),
        new THREE.Vector3(...R[1]),
        new THREE.Vector3(...R[2])
      );
      this.objects.get(object_id).rotation.setFromRotationMatrix(R4.transpose());
    },
    visible(object_id, value) {
      if (!this.objects.has(object_id)) return;
      this.objects.get(object_id).visible = value;
    },
    draggable(object_id, value) {
      if (!this.objects.has(object_id)) return;
      const object = this.objects.get(object_id);
      if (value) this.draggable_objects.push(object);
      else {
        const index = this.draggable_objects.indexOf(object);
        if (index != -1) this.draggable_objects.splice(index, 1);
      }
    },
    delete(object_id) {
      if (!this.objects.has(object_id)) return;
      // Clean up any transform controls attached to this object
      this.disable_transform_controls(object_id);
      const object = this.objects.get(object_id);
      object.removeFromParent();
      this.objects.delete(object_id);
      const index = this.draggable_objects.indexOf(object);
      if (index != -1) this.draggable_objects.splice(index, 1);
    },
    enable_transform_controls(object_id, mode, size, visible_axes) {
      if (!this.objects.has(object_id)) {
        return false;
      }
      // If already has transform controls, just update mode and axes
      if (this.transform_controls.has(object_id)) {
        const tc = this.transform_controls.get(object_id);
        tc.setMode(mode);
        if (size !== undefined && size !== null) {
          tc.setSize(size);
        }
        // Update axis visibility if provided
        if (visible_axes !== undefined && visible_axes !== null) {
          tc.showX = visible_axes.includes('X');
          tc.showY = visible_axes.includes('Y');
          tc.showZ = visible_axes.includes('Z');
        } else {
          // Show all axes if not specified
          tc.showX = true;
          tc.showY = true;
          tc.showZ = true;
        }

        // Axis lock for single-axis rotate
        if (mode === "rotate" && Array.isArray(visible_axes) && visible_axes.length === 1) {
          const lockAxis = visible_axes[0];
          if (!tc.userData) tc.userData = {};
          tc.userData.lockAxis = lockAxis;
          tc.axis = lockAxis;
        } else {
          // Clear axis lock if multiple axes or not rotate mode
          if (tc.userData) delete tc.userData.lockAxis;
        }
        return true;
      }
      const object = this.objects.get(object_id);
      const tc = new TransformControls(this.camera, this.renderer.domElement);
      tc.attach(object);
      tc.setMode(mode); // 'translate', 'rotate', or 'scale'
      if (mode === "translate") {
        // Use world space for translation to avoid local-axis confusion (especially for TCP ball)
        tc.setSpace("world");
      }
      if (size !== undefined && size !== null) {
        tc.setSize(size);
      }
      // Set axis visibility if provided
      if (visible_axes !== undefined && visible_axes !== null) {
        tc.showX = visible_axes.includes('X');
        tc.showY = visible_axes.includes('Y');
        tc.showZ = visible_axes.includes('Z');
        // If a single axis is shown in rotate mode, lock to that axis
        if (mode === "rotate" && Array.isArray(visible_axes) && visible_axes.length === 1) {
          const lockAxis = visible_axes[0];
          if (!tc.userData) tc.userData = {};
          tc.userData.lockAxis = lockAxis;
        }
      }
      // Track dragging state to only emit transform events during actual user interaction
      let isDragging = false;
      
      // Disable orbit controls while transforming - using reference counting to handle multiple TransformControls
      tc.addEventListener("dragging-changed", (event) => {
        const prevCount = this.dragging_count;
        isDragging = event.value;
        
        if (event.value) {
          // Starting to drag - increment count
          this.dragging_count++;
          // Only disable orbit if this is the first one dragging
          if (this.dragging_count === 1) {
            this.controls.enabled = false;
          }
        } else {
          // Stopped dragging - decrement count (but not below 0)
          this.dragging_count = Math.max(0, this.dragging_count - 1);
          // Only re-enable orbit if no one is dragging anymore
          if (this.dragging_count === 0) {
            this.controls.enabled = true;
          }
        }
        
      });
      // Emit transform events only while actively dragging
      tc.addEventListener("change", () => {
        // Only emit transform events when user is actively dragging
        // TransformControls fires 'change' on every render frame when attached,
        // but we only want to emit events during actual user interaction
        if (!isDragging) return;

        // Enforce axis lock for single-axis rotate
        if (tc.mode === "rotate" && tc.userData && tc.userData.lockAxis && tc.axis !== tc.userData.lockAxis) {
          tc.axis = tc.userData.lockAxis;
        }

        // Compute world position for consumers that need absolute coordinates
        const wp = new THREE.Vector3();
        object.getWorldPosition(wp);
        
        // The dragging-changed log above shows when drag starts/stops
        this.$emit("transform", {
          type: "transform",
          object_id: object_id,
          object_name: object.name,
          // Local coordinates (relative to parent)
          x: object.position.x,
          y: object.position.y,
          z: object.position.z,
          // World coordinates (absolute)
          wx: wp.x,
          wy: wp.y,
          wz: wp.z,
          // Local rotation
          rx: object.rotation.x,
          ry: object.rotation.y,
          rz: object.rotation.z,
          mode: tc.mode,
        });
      });
      tc.addEventListener("mouseDown", () => {
        // If axis lock defined, force it on press
        if (tc.userData && tc.userData.lockAxis) {
          tc.axis = tc.userData.lockAxis;
        }
        this.$emit("transform_start", {
          type: "transform_start",
          object_id: object_id,
          object_name: object.name,
          x: object.position.x,
          y: object.position.y,
          z: object.position.z,
          rx: object.rotation.x,
          ry: object.rotation.y,
          rz: object.rotation.z,
          mode: tc.mode,
        });
      });
      tc.addEventListener("mouseUp", () => {
        this.$emit("transform_end", {
          type: "transform_end",
          object_id: object_id,
          object_name: object.name,
          x: object.position.x,
          y: object.position.y,
          z: object.position.z,
          rx: object.rotation.x,
          ry: object.rotation.y,
          rz: object.rotation.z,
          mode: tc.mode,
        });
      });
      this.scene.add(tc.getHelper());
      // Tag all TransformControls gizmo parts so they appear in raycaster hits
      // NOTE: Only set object_id, do NOT overwrite name - TransformControls uses
      // name internally to identify which handle (X, Y, Z, etc.) was clicked
      tc.getHelper().traverse((child) => {
        child.object_id = `transformcontrols:${object_id}`;
      });
      this.transform_controls.set(object_id, tc);
      return true;
    },
    disable_transform_controls(object_id) {
      if (!this.transform_controls.has(object_id)) return;
      const tc = this.transform_controls.get(object_id);
      
      // If this TC was actively dragging, decrement the count before disposal
      // TransformControls.dragging property tracks current drag state
      // The dragging-changed event won't fire after dispose(), so we must handle it here
      if (tc.dragging) {
        this.dragging_count = Math.max(0, this.dragging_count - 1);
      }
      
      tc.detach();
      this.scene.remove(tc.getHelper());
      tc.dispose();
      this.transform_controls.delete(object_id);
      
      // Re-enable orbit if no other TransformControls are dragging
      if (this.dragging_count === 0) {
        this.controls.enabled = true;
      }
    },
    set_transform_mode(object_id, mode) {
      if (!this.transform_controls.has(object_id)) return;
      const tc = this.transform_controls.get(object_id);
      tc.setMode(mode);
    },
    set_transform_size(object_id, size) {
      if (!this.transform_controls.has(object_id)) return;
      const tc = this.transform_controls.get(object_id);
      tc.setSize(size);
    },
    set_transform_space(object_id, space) {
      if (!this.transform_controls.has(object_id)) return;
      const tc = this.transform_controls.get(object_id);
      tc.setSpace(space);
    },
    set_transform_rotation_snap(object_id, radians) {
      if (!this.transform_controls.has(object_id)) return;
      const tc = this.transform_controls.get(object_id);
      tc.setRotationSnap(radians);
    },
    has_transform_controls(object_id) {
      return this.transform_controls.has(object_id);
    },

    // Set clipping planes for an object (for proximity-based envelope visibility)
    // planes: array of {nx, ny, nz, d} defining plane normals and distances
    set_clipping_planes(object_id, planes) {
      if (!this.objects.has(object_id)) return;
      const object = this.objects.get(object_id);
      const clipPlanes = planes.map(p => new THREE.Plane(
        new THREE.Vector3(p.nx, p.ny, p.nz).normalize(),
        p.d
      ));
      // Apply to object and all descendants
      object.traverse((child) => {
        if (child.material) {
          const mats = Array.isArray(child.material) ? child.material : [child.material];
          mats.forEach(mat => {
            mat.clippingPlanes = clipPlanes;
            mat.clipIntersection = false; // Clip where ANY plane clips (union)
            mat.needsUpdate = true;
          });
        }
      });
    },

    // Clear clipping planes from an object
    clear_clipping_planes(object_id) {
      if (!this.objects.has(object_id)) return;
      const object = this.objects.get(object_id);
      object.traverse((child) => {
        if (child.material) {
          const mats = Array.isArray(child.material) ? child.material : [child.material];
          mats.forEach(mat => {
            mat.clippingPlanes = null;
            mat.needsUpdate = true;
          });
        }
      });
    },

    // Configure axes inset (position, size, anchor, enabled) at runtime (opt-in, lazy)
    // opts: { enabled?: boolean, size?: number, margin?: number, marginX?: number, marginY?: number,
    //         anchor?: "bottom-left"|"bottom-right"|"top-left"|"top-right" }
    set_axes_inset(opts) {
      const prev = this._axes || {};
      this._axes = Object.assign({}, prev, opts || {});
      const enabled = !!this._axes.enabled;
      if (enabled) {
        if (!this.axesScene || !this.axesCamera) {
          this.axesScene = new THREE.Scene();
          this.axesCamera = new THREE.PerspectiveCamera(50, 1, 0.1, 10);
          this.axesHelper = new THREE.AxesHelper(0.6);
          if (this.axesHelper.material) {
            const mats = Array.isArray(this.axesHelper.material) ? this.axesHelper.material : [this.axesHelper.material];
            mats.forEach((m) => {
              m.transparent = true;
              m.opacity = 0.95;
              m.depthTest = false;
            });
          }
          this.axesScene.add(this.axesHelper);
          // If labels were requested before creation, create now
          if (this._axesLabels && this._axesLabels.enabled && !this.axesLabels) {
            this.set_axes_labels({ enabled: true });
          }
        }
      } else {
        // disable inset and free objects
        this.axesScene = null;
        this.axesCamera = null;
        this.axesHelper = null;
        this.axesLabels = null;
      }
    },

    // Configure axis labels (X,Y,Z) for orientation inset (opt-in, lazy)
    // opts: { enabled?: boolean, font?: string, colorX?: string, colorY?: string, colorZ?: string, size?: number }
    set_axes_labels(opts) {
      this._axesLabels = Object.assign({}, this._axesLabels || {}, opts || {});
      const enabled = !!this._axesLabels.enabled;
      if (!this.axesScene || !this.axesCamera) return;
      if (enabled && !this.axesLabels) {
        const createAxisLabel = (text, color, position) => {
          const canvas = document.createElement("canvas");
          const ctx = canvas.getContext("2d");
          if (!ctx) return null;
          const padding = 8;
          const font = this._axesLabels.font || "bold 32px sans-serif";
          ctx.font = font;
          const metrics = ctx.measureText(text);
          const w = Math.ceil(metrics.width) + padding * 2;
          const h = 48 + padding * 2;
          canvas.width = w;
          canvas.height = h;
          const ctx2 = canvas.getContext("2d");
          if (!ctx2) return null;
          ctx2.font = font;
          ctx2.textAlign = "center";
          ctx2.textBaseline = "middle";
          ctx2.lineWidth = 6;
          ctx2.strokeStyle = "rgba(0,0,0,0.5)";
          ctx2.strokeText(text, w / 2, h / 2);
          ctx2.fillStyle = color;
          ctx2.fillText(text, w / 2, h / 2);
          const tex = new THREE.CanvasTexture(canvas);
          tex.minFilter = THREE.LinearFilter;
          const mat = new THREE.SpriteMaterial({ map: tex, transparent: true, depthTest: false });
          const sprite = new THREE.Sprite(mat);
          sprite.position.copy(position);
          const s = (this._axesLabels.size || 0.35);
          sprite.scale.set(s, s, 1);
          return sprite;
        };
        this.axesLabels = {};
        const cx = this._axesLabels.colorX || "#d94c3f";
        const cy = this._axesLabels.colorY || "#2faf7a";
        const cz = this._axesLabels.colorZ || "#4a63e0";
        const lblX = createAxisLabel("X", cx, new THREE.Vector3(0.8, 0, 0));
        const lblY = createAxisLabel("Y", cy, new THREE.Vector3(0, 0.8, 0));
        const lblZ = createAxisLabel("Z", cz, new THREE.Vector3(0, 0, 0.8));
        [lblX, lblY, lblZ].forEach((s) => { if (s) this.axesScene.add(s); });
        this.axesLabels.X = lblX;
        this.axesLabels.Y = lblY;
        this.axesLabels.Z = lblZ;
      } else if (!enabled && this.axesLabels) {
        for (const key of Object.keys(this.axesLabels)) {
          const spr = this.axesLabels[key];
          if (spr && spr.parent) this.axesScene.remove(spr);
        }
        this.axesLabels = null;
      }
    },

    // Explicitly toggle OrbitControls enabled state (used by Python side)
    set_orbit_enabled(flag) {
      this.controls.enabled = !!flag;
    },
    set_texture_url(object_id, url) {
      if (!this.objects.has(object_id)) return;
      const obj = this.objects.get(object_id);
      if (obj.busy) return;
      obj.busy = true;
      const on_success = (texture) => {
        obj.material = texture_material(texture);
        obj.busy = false;
      };
      const on_error = () => (obj.busy = false);
      this.texture_loader.load(url, on_success, undefined, on_error);
    },
    set_texture_coordinates(object_id, coords) {
      if (!this.objects.has(object_id)) return;
      this.objects.get(object_id).geometry = texture_geometry(coords);
    },
    set_points(object_id, position, color) {
      if (!this.objects.has(object_id)) return;
      const geometry = this.objects.get(object_id).geometry;
      set_point_cloud_data(position, color, geometry);
    },
    attach(object_id, parent_id, x, y, z, R) {
      if (!this.objects.has(object_id)) return;
      const object = this.objects.get(object_id);
      const parent = this.objects.get(parent_id);
      parent.add(object);
      this.move(object_id, x, y, z);
      this.rotate(object_id, R);
    },
    detach(object_id, x, y, z, R) {
      if (!this.objects.has(object_id)) return;
      const object = this.objects.get(object_id);
      object.removeFromParent();
      this.scene.add(object);
      this.move(object_id, x, y, z);
      this.rotate(object_id, R);
    },
    move_camera(x, y, z, look_at_x, look_at_y, look_at_z, up_x, up_y, up_z, duration) {
      if (this.camera_tween) this.camera_tween.stop();
      const camera_up_changed = up_x !== null || up_y !== null || up_z !== null;
      this.camera_tween = new TWEEN.Tween([
        this.camera.position.x,
        this.camera.position.y,
        this.camera.position.z,
        this.camera.up.x,
        this.camera.up.y,
        this.camera.up.z,
        this.look_at.x,
        this.look_at.y,
        this.look_at.z,
      ])
        .to(
          [
            x === null ? this.camera.position.x : x,
            y === null ? this.camera.position.y : y,
            z === null ? this.camera.position.z : z,
            up_x === null ? this.camera.up.x : up_x,
            up_y === null ? this.camera.up.y : up_y,
            up_z === null ? this.camera.up.z : up_z,
            look_at_x === null ? this.look_at.x : look_at_x,
            look_at_y === null ? this.look_at.y : look_at_y,
            look_at_z === null ? this.look_at.z : look_at_z,
          ],
          duration * 1000
        )
        .onUpdate((p) => {
          this.camera.position.set(p[0], p[1], p[2]);
          this.camera.up.set(p[3], p[4], p[5]); // NOTE: before calling lookAt
          this.look_at.set(p[6], p[7], p[8]);
          this.camera.lookAt(p[6], p[7], p[8]);
          this.controls.target.set(p[6], p[7], p[8]);
        })
        .onComplete(() => {
          if (camera_up_changed) {
            this.controls.dispose();
            this.controls = new OrbitControls(this.camera, this.renderer.domElement);
            this.controls.target.copy(this.look_at);
            this.camera.lookAt(this.look_at);
          }
        })
        .start();
    },
    get_camera() {
      return {
        position: this.camera.position,
        up: this.camera.up,
        rotation: this.camera.rotation,
        quaternion: this.camera.quaternion,
        type: this.camera.type,
        fov: this.camera.fov,
        aspect: this.camera.aspect,
        near: this.camera.near,
        far: this.camera.far,
        left: this.camera.left,
        right: this.camera.right,
        top: this.camera.top,
        bottom: this.camera.bottom,
      };
    },
    resize() {
      const { clientWidth, clientHeight } = this.$el;
      this.renderer.setSize(clientWidth, clientHeight);
      this.text_renderer.setSize(clientWidth, clientHeight);
      this.text3d_renderer.setSize(clientWidth, clientHeight);
      this.camera.aspect = clientWidth / clientHeight;
      if (this.camera_type === "orthographic") {
        this.camera.left = (-this.camera.aspect * this.camera_params.size) / 2;
        this.camera.right = (this.camera.aspect * this.camera_params.size) / 2;
      }
      this.camera.updateProjectionMatrix();
    },
    init_objects(data) {
      this.resize();
      this.$el.removeAttribute("data-initializing");
      this.is_initialized = true;
      for (const [
        type,
        id,
        parent_id,
        args,
        name,
        color,
        opacity,
        side,
        x,
        y,
        z,
        R,
        sx,
        sy,
        sz,
        visible,
        draggable,
      ] of data) {
        this.create(type, id, parent_id, ...args);
        this.name(id, name);
        this.material(id, color, opacity, side);
        this.move(id, x, y, z);
        this.rotate(id, R);
        this.scale(id, sx, sy, sz);
        this.visible(id, visible);
        this.draggable(id, draggable);
      }
    },
  },

  props: {
    width: Number,
    height: Number,
    grid: Object,
    polar_grid: Array,
    camera_type: String,
    camera_params: Object,
    click_events: Array,
    drag_constraints: String,
    background_color: String,
    fps: Number,
    show_stats: Boolean,
  },
};
