(() => {
  window.WatchAPI = async (path, options = {}) => {
    const response = await fetch(path, {
      ...options,
      headers: { 'Content-Type': 'application/json', 'X-Watchlists-Request': '1', ...options.headers },
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
      credentials: 'same-origin', cache: 'no-store'
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const detail = data.detail;
      throw new Error(typeof detail === 'string' ? detail : 'Das hat nicht geklappt. Bitte erneut versuchen.');
    }
    return data;
  };
})();
