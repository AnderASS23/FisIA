/* Puente entre la página y el servidor local.
   La página original pide a "claude.use('sample')" (IA) y "claude.use('downloads')" (guardar archivos).
   Aquí se implementan con el servidor Flask y con una descarga normal del navegador. */
(function () {
  'use strict';

  const RS = '\x1e'; // separador: lo que sigue es un error JSON enviado a mitad de la respuesta

  async function estado() {
    try {
      const r = await fetch('/api/estado');
      return await r.json();
    } catch (e) {
      return {ia: false, audio: false};
    }
  }

  // Una sola consulta a la vez y una pausa mínima entre ellas: evita picos de peticiones a la IA.
  let cola = Promise.resolve();
  let ultimaFin = 0;
  const PAUSA_MS = 900;

  function sample(input, opts) {
    opts = opts || {};
    const turno = cola.then(async function () {
      if (opts.signal && opts.signal.aborted) throw {code: 'cancelled', message: 'Cancelado'};
      const falta = PAUSA_MS - (Date.now() - ultimaFin);
      if (falta > 0) await new Promise(function (r) { setTimeout(r, falta); });
      try { return await consulta(input, opts); } finally { ultimaFin = Date.now(); }
    });
    cola = turno.catch(function () {});
    return turno;
  }

  async function consulta(input, opts) {
    const mensajes = typeof input === 'string' ? [{role: 'user', content: input}] : input;
    const fd = new FormData();
    fd.append('messages', JSON.stringify(mensajes));
    fd.append('tier', opts.modelTier || 'default');
    if (opts.kind) fd.append('kind', opts.kind);
    if (opts.system) fd.append('system', opts.system);
    const imgs = !opts.images ? [] : (opts.images instanceof Blob ? [opts.images] : Array.from(opts.images));
    imgs.forEach((b, i) => fd.append('images', b, 'imagen' + i));

    let resp;
    try {
      resp = await fetch('/api/sample', {method: 'POST', body: fd, signal: opts.signal});
    } catch (e) {
      if (e && e.name === 'AbortError') throw {code: 'cancelled', message: 'Cancelado'};
      throw {code: 'upstream_error', message: 'No hay conexión con el servidor local. ¿Sigue corriendo python app.py?'};
    }
    if (!resp.ok) {
      let j = {};
      try { j = await resp.json(); } catch (e) { /* sin cuerpo JSON */ }
      throw {code: j.code || 'upstream_error', message: j.message || ('Error HTTP ' + resp.status), retry_after: j.retry_after};
    }

    const lector = resp.body.getReader();
    const dec = new TextDecoder();
    let crudo = '';
    let mostrado = '';
    try {
      for (;;) {
        const {done, value} = await lector.read();
        if (done) break;
        crudo += dec.decode(value, {stream: true});
        const i = crudo.indexOf(RS);
        const visible = i < 0 ? crudo : crudo.slice(0, i);
        if (visible.length > mostrado.length && visible.trim()) {
          const delta = visible.slice(mostrado.length);
          mostrado = visible;
          if (opts.onText) opts.onText({text: mostrado, delta});
        }
      }
    } catch (e) {
      if (e && e.name === 'AbortError') throw {code: 'cancelled', message: 'Cancelado', text: mostrado};
      throw {code: 'upstream_error', message: 'Se interrumpió la conexión con la IA.', text: mostrado};
    }

    const i = crudo.indexOf(RS);
    if (i >= 0) {
      let err = {};
      try { err = JSON.parse(crudo.slice(i + 1)); } catch (e) { /* error ilegible */ }
      throw {code: err.code || 'upstream_error', message: err.message || 'La respuesta se interrumpió.', text: mostrado, retry_after: err.retry_after};
    }
    if (!mostrado.trim()) throw {code: 'empty_completion', message: 'La IA no devolvió texto.'};
    return {text: mostrado, truncated: false, cached: resp.headers.get('X-Fisia-Cache') === 'hit', modelTierApplied: opts.modelTier || 'default'};
  }

  sample.limits = async function () {
    return {
      maxPromptBytes: 262144,
      images: {maxCount: 4, maxInputBytes: 20 * 1024 * 1024, mediaTypes: ['image/jpeg', 'image/png', 'image/webp', 'image/gif']}
    };
  };
  sample.json = async function (input, opts) {
    const r = await sample(input, opts);
    return JSON.parse(r.text);
  };

  const descargas = {
    save: async function (req) {
      const blob = req.data instanceof Blob ? req.data : new Blob([req.data]);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = req.filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(function () { URL.revokeObjectURL(url); }, 4000);
      return {status: 'saved'};
    }
  };

  window.claude = {
    use: async function (nombre) {
      if (nombre === 'sample') {
        const e = await estado();
        return e.ia ? sample : null;
      }
      if (nombre === 'downloads') return descargas;
      return null;
    }
  };
})();
