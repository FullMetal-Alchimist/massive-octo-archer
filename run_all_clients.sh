echo "Running all clients now."

for file in ./Clients/* ; do
	if [ -e "$file" ] ; then
		echo "Running client $file"
		python "$file" $1 $2 &
	fi
done