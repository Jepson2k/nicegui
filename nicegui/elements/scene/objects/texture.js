import { THREE } from "nicegui-scene";

const texture_loader = new THREE.TextureLoader();

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

export default class Texture {
  busy = false;

  // Loads are awaited, so the scene's method call finishes, and a render-on-demand scene draws, once the image is in.
  async create_mesh(url, coords) {
    this.mesh = new THREE.Mesh(texture_geometry(coords), texture_material(await texture_loader.loadAsync(url)));
    return this.mesh;
  }
  async set_url(url) {
    if (this.busy) {
      console.warn("Can't set the texture URL; another `set_url` operation is already running");
      return;
    }
    this.busy = true;
    try {
      this.mesh.material = texture_material(await texture_loader.loadAsync(url));
    } finally {
      this.busy = false;
    }
  }
  set_coordinates(coords) {
    this.mesh.geometry = texture_geometry(coords);
  }
}
