# Milk Business Management System - PWA & Build Setup

## Quick Start

### Development Setup

1. **Install Python dependencies:**
   ```bash
   .venv/Scripts/pip install -r requirements.txt  # (if you have one)
   # Or: .venv/Scripts/pip install django
   ```

2. **Install Node dependencies:**
   ```bash
   npm install
   ```

3. **Start Tailwind CSS watch mode (in separate terminal):**
   ```bash
   npm run tailwind:watch
   ```

4. **Run Django development server:**
   ```bash
   .venv/Scripts/python manage.py runserver
   ```

Visit: `http://localhost:8000`

### Production Build

1. **Build Tailwind CSS (minified):**
   ```bash
   npm run tailwind:build
   ```

2. **Collect static files:**
   ```bash
   python manage.py collectstatic --noinput
   ```

3. **Deploy with your web server** (Gunicorn, uWSGI, etc.)

## PWA Features

✅ **Installable as app** - Add to home screen on mobile  
✅ **Offline support** - Service worker caches pages  
✅ **App icon** - Custom icon in home screen  
✅ **Standalone mode** - Runs without browser chrome  
✅ **App shortcuts** - Quick access to key pages  

### Testing PWA

**Android (Chrome):**
- Open app → Menu → "Install app"

**iOS (Safari):**
- Open app → Share → "Add to Home Screen"

**Desktop (Chrome DevTools):**
1. F12 → Application tab
2. Check Manifest, Service Workers, Cache Storage
3. Right-click → "Install"

## CSS/Styling

- **Tailwind CSS** - Utility-first CSS framework (compiled locally)
- **Custom CSS** - `static/css/app.css` for additional styles
- **Responsive** - Mobile-first design with breakpoints

### Customizing Styles

Edit `static/css/app.css` for custom styles that don't exist in Tailwind.

Edit `tailwind.config.js` to customize Tailwind configuration.

After changes, rebuild:
```bash
npm run tailwind:build
```

## Files Structure

```
.
├── static/
│   ├── css/
│   │   ├── tailwind.css          (Generated - don't edit)
│   │   ├── tailwind.input.css    (Tailwind source)
│   │   └── app.css               (Custom styles)
│   ├── js/
│   │   └── app.js
│   ├── icons/                    (PWA icons)
│   ├── images/
│   └── manifest.json             (PWA manifest)
├── service-worker.js             (Offline support)
├── templates/base.html           (Main template with PWA tags)
├── package.json                  (Node dependencies)
├── tailwind.config.js            (Tailwind config)
├── postcss.config.js             (PostCSS config)
└── manage.py                     (Django)
```

## Troubleshooting

**PWA won't install:**
- Ensure you're on HTTPS (or localhost)
- Check manifest.json is valid
- Icons must be valid PNG files
- Service worker must be registered

**Styles look broken:**
- Run `npm run tailwind:build` to rebuild CSS
- Clear browser cache (Ctrl+Shift+Delete)

**Service Worker issues:**
- Check browser console for errors
- DevTools → Application → Service Workers
- Unregister and refresh to re-register

## Next Steps

1. ✅ PWA setup complete
2. ✅ Tailwind CSS configured
3. Generate proper app icons (replace placeholder icons)
4. Test on multiple devices
5. Deploy to production with HTTPS
