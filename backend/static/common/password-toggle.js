(function () {
    function enhancePasswordFields(root) {
        (root || document).querySelectorAll('input[type="password"]:not([data-password-toggle-ready])').forEach(function (input) {
            input.setAttribute('data-password-toggle-ready', 'true');

            var wrapper = document.createElement('span');
            wrapper.className = 'password-toggle-wrap';
            wrapper.style.cssText = 'display:block;position:relative;width:100%;';
            input.parentNode.insertBefore(wrapper, input);
            wrapper.appendChild(input);
            input.style.paddingRight = '44px';

            var button = document.createElement('button');
            button.type = 'button';
            button.className = 'password-toggle-button';
            button.setAttribute('aria-label', 'Show password');
            button.innerHTML = '<span aria-hidden="true">👁</span>';
            button.style.cssText = 'position:absolute;top:50%;right:10px;transform:translateY(-50%);border:0;background:transparent;color:#718096;cursor:pointer;padding:6px;line-height:1;font-size:16px;z-index:2;';

            button.addEventListener('click', function () {
                var visible = input.type === 'text';
                input.type = visible ? 'password' : 'text';
                button.setAttribute('aria-label', visible ? 'Show password' : 'Hide password');
                button.innerHTML = visible ? '<span aria-hidden="true">👁</span>' : '<span aria-hidden="true">🙈</span>';
            });
            wrapper.appendChild(button);
        });
    }

    document.addEventListener('DOMContentLoaded', function () {
        enhancePasswordFields(document);
    });
})();
